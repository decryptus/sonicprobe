"""SQLite transaction boundaries and WAL concurrency, using synthetic data."""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
try:
    from unittest import mock
except ImportError:
    import mock

from sonicprobe.libs import anysql
from sonicprobe.libs.sqlite_transactions import SQLiteTransactions


class SQLiteTransactionTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        self.uri = 'sqlite3:' + os.path.join(root, 'state.db') + '?timeout_ms=30'
        self.first, self.left = self.open()
        self.first.driver_connection.execute('PRAGMA journal_mode=WAL')
        self.first.driver_connection.execute('CREATE TABLE items (id INTEGER PRIMARY KEY)')
        self.second, self.right = self.open()

    def open(self):
        connection = anysql.connect_by_uri(self.uri, auto_reconnect=False)
        self.addCleanup(connection.close)
        connection.driver_connection.isolation_level = None
        return connection, SQLiteTransactions(connection)

    def values(self, connection):
        return connection.driver_connection.execute('SELECT id FROM items ORDER BY id').fetchall()

    def test_read_snapshot_does_not_reserve_writer_and_keeps_committed_view(self):
        with self.left.read_snapshot() as connection:
            self.assertIs(connection, self.first)
            self.assertEqual(self.values(self.first), [])
            with self.right.transaction():
                self.second.driver_connection.execute('INSERT INTO items VALUES (1)')
            self.assertEqual(self.values(self.first), [])
        self.assertEqual(self.values(self.first), [(1,)])

    def test_new_connection_reads_while_another_writer_is_uncommitted(self):
        with self.left.transaction():
            self.first.driver_connection.execute('INSERT INTO items VALUES (1)')
            third, transactions = self.open()
            with transactions.read_snapshot():
                self.assertEqual(self.values(third), [])
        self.assertEqual(self.values(third), [(1,)])

    def test_writer_contention_preserves_timeout_and_never_reconnects(self):
        with mock.patch.object(self.second, 'reconnect') as reconnect:
            with self.left.transaction():
                with self.assertRaises(sqlite3.OperationalError):
                    with self.right.transaction():
                        self.fail('second writer acquired the reservation')
            self.assertFalse(reconnect.called)
        with self.right.transaction():
            self.second.driver_connection.execute('INSERT INTO items VALUES (2)')
        self.assertEqual(self.values(self.first), [(2,)])

    def test_failure_rolls_back_all_joined_writes_and_domain_can_be_reused(self):
        class Cancelled(BaseException):
            pass
        with self.assertRaises(Cancelled):
            with self.left.transaction():
                with self.left.transaction():
                    self.first.driver_connection.execute('INSERT INTO items VALUES (1)')
                raise Cancelled()
        self.assertEqual(self.values(self.second), [])
        with self.left.transaction():
            self.first.driver_connection.execute('INSERT INTO items VALUES (2)')
        self.assertEqual(self.values(self.second), [(2,)])

    def test_nested_read_cannot_be_upgraded_to_managed_write(self):
        with self.left.read_snapshot():
            with self.left.read_snapshot():
                self.assertEqual(self.values(self.first), [])
            with self.assertRaises(ValueError):
                with self.left.transaction():
                    self.fail('upgraded a snapshot')
        with self.left.transaction():
            with self.left.read_snapshot():
                with self.left.transaction():
                    self.first.driver_connection.execute('INSERT INTO items VALUES (1)')
        self.assertEqual(self.values(self.second), [(1,)])

    @unittest.skipIf(sys.version_info < (3, 6), 'Legacy sqlite3 implicitly commits DDL')
    def test_snapshot_can_use_connection_local_temporary_tables(self):
        with self.left.read_snapshot():
            self.assertEqual(self.values(self.first), [])
            self.first.driver_connection.execute('CREATE TEMP TABLE selected (id INTEGER)')
            self.first.driver_connection.execute('INSERT INTO selected VALUES (1)')
            with self.right.transaction():
                self.second.driver_connection.execute('INSERT INTO items VALUES (1)')
            self.assertEqual(self.values(self.first), [])
            self.first.driver_connection.execute('DROP TABLE selected')
        self.assertEqual(self.values(self.first), [(1,)])

    def test_rejects_replay_implicit_transactions_and_other_drivers(self):
        with self.assertRaises(ValueError):
            SQLiteTransactions(mock.Mock(auto_reconnect=True))
        with self.assertRaises(TypeError):
            SQLiteTransactions(mock.Mock(auto_reconnect=False))
        connection = anysql.connect_by_uri('sqlite3::memory:', auto_reconnect=False)
        self.addCleanup(connection.close)
        with self.assertRaises(ValueError):
            SQLiteTransactions(connection)

    def test_failed_begin_leaves_external_transaction_owned_by_caller(self):
        self.first.driver_connection.execute('BEGIN')
        self.first.driver_connection.execute('INSERT INTO items VALUES (1)')
        with self.assertRaises(sqlite3.OperationalError):
            with self.left.transaction():
                self.fail('joined an unmanaged transaction')
        self.first.driver_connection.execute('COMMIT')
        self.assertEqual(self.values(self.second), [(1,)])

    def test_explicit_reconnection_invalidates_existing_transaction_domain(self):
        self.first.close()
        self.first.reconnect()
        with self.assertRaises(ValueError):
            with self.left.read_snapshot():
                self.fail('used a replaced driver connection')

    def test_commit_failure_is_not_replayed_and_rolls_back(self):
        raw = self.first.driver_connection
        raw.execute('PRAGMA foreign_keys=ON')
        raw.execute('CREATE TABLE child (id INTEGER REFERENCES items(id) DEFERRABLE INITIALLY DEFERRED)')
        with mock.patch.object(self.first, 'reconnect') as reconnect:
            with self.assertRaises(sqlite3.IntegrityError):
                with self.left.transaction():
                    raw.execute('INSERT INTO child VALUES (99)')
            self.assertFalse(reconnect.called)
        self.assertEqual(raw.execute('SELECT * FROM child').fetchall(), [])
        with self.left.transaction():
            raw.execute('INSERT INTO items VALUES (99)')
            raw.execute('INSERT INTO child VALUES (99)')

    def test_cleanup_failure_preserves_original_error_and_prevents_reuse(self):
        failure = RuntimeError('synthetic failure')
        with self.assertRaises(RuntimeError) as caught:
            with self.left.transaction():
                self.first.close()
                raise failure
        self.assertIs(caught.exception, failure)
        with self.assertRaises(RuntimeError):
            with self.left.transaction():
                self.fail('reused a failed transaction domain')
