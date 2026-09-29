"""Evaluate strict transaction failure behavior without changing legacy defaults."""
import os
import shutil
import sqlite3
import tempfile
import unittest
try:
    from unittest import mock
except ImportError:
    import mock
from sonicprobe.libs import anysql


class ReconnectPolicyTests(unittest.TestCase):
    def test_closed_sqlite_commit_raises_in_strict_mode(self):
        conn = anysql.connect_by_uri('sqlite3::memory:', auto_reconnect=False)
        cursor = conn.cursor()
        cursor.query('CREATE TABLE items (id INTEGER PRIMARY KEY)')
        cursor.query('INSERT INTO items VALUES (?)', parameters=[1])
        conn.close()
        with mock.patch.object(conn, 'reconnect') as reconnect:
            with self.assertRaises(sqlite3.ProgrammingError):
                conn.commit()
            reconnect.assert_not_called()

    def test_legacy_commit_still_reconnects_by_default(self):
        conn = anysql.connect_by_uri('sqlite3::memory:')
        self.addCleanup(conn.close)
        self.assertTrue(conn.auto_reconnect)
        conn.close()
        conn.commit()
        self.assertTrue(conn.is_connected())

    def test_closed_query_and_fetches_never_reconnect_in_strict_mode(self):
        for method in ('query', 'fetchone', 'fetchmany', 'fetchall'):
            conn = anysql.connect_by_uri('sqlite3::memory:', auto_reconnect=False)
            cursor = conn.cursor()
            cursor.query('SELECT 1')
            conn.close()
            with mock.patch.object(conn, 'reconnect') as reconnect:
                with self.assertRaises(sqlite3.ProgrammingError):
                    if method == 'query':
                        cursor.query('SELECT 2')
                    else:
                        getattr(cursor, method)()
                reconnect.assert_not_called()

    def test_querymany_driver_failure_does_not_probe_or_replay(self):
        conn = mock.Mock(auto_reconnect=False)
        raw = conn._get_raw_cursor.return_value
        failure = RuntimeError('driver failure')
        raw.executemany.side_effect = failure
        methods = [None] * (anysql.METHOD_MODULE + 1)
        methods[anysql.METHOD_MODULE] = mock.Mock(paramstyle='format')
        cursor = anysql.cursor(conn, methods)
        with self.assertRaises(RuntimeError) as caught:
            cursor.querymany('INSERT INTO items VALUES (%s)', None, [[1], [2]])
        self.assertIs(caught.exception, failure)
        self.assertEqual(raw.executemany.call_count, 1)
        conn.is_connected.assert_not_called()
        conn.reconnect.assert_not_called()

    def test_sqlite_durable_transactions_lock_timeout_and_recovery(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory)
        uri = 'sqlite3:' + os.path.join(directory, 'state.db') + '?timeout_ms=50'
        first = anysql.connect_by_uri(uri, auto_reconnect=False)
        second = anysql.connect_by_uri(uri, auto_reconnect=False)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        left, right = first.cursor(), second.cursor()
        left.query('CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT)')
        first.commit()
        left.query('BEGIN IMMEDIATE')
        left.query('INSERT INTO items VALUES (?, ?)', parameters=[1, 'kept'])
        with mock.patch.object(second, 'reconnect') as reconnect:
            with self.assertRaises(sqlite3.OperationalError):
                right.query('BEGIN IMMEDIATE')
            reconnect.assert_not_called()
        first.commit()
        right.query('BEGIN IMMEDIATE')
        right.query('INSERT INTO items VALUES (?, ?)', parameters=[2, 'rolled back'])
        second.rollback()
        reopened = anysql.connect_by_uri(uri, auto_reconnect=False)
        try:
            cursor = reopened.cursor()
            cursor.query('SELECT id, value FROM items ORDER BY id')
            self.assertEqual(cursor.fetchall(raw=True), [(1, 'kept')])
        finally:
            reopened.close()

    def test_reconnect_setting_is_per_connection_and_requires_boolean(self):
        strict = anysql.connect_by_uri('sqlite3::memory:', auto_reconnect=False)
        legacy = anysql.connect_by_uri('sqlite3::memory:')
        self.addCleanup(strict.close)
        self.addCleanup(legacy.close)
        self.assertFalse(strict.auto_reconnect)
        self.assertTrue(legacy.auto_reconnect)
        for value in ('false', 0, None):
            with self.assertRaises(ValueError):
                anysql.connect_by_uri('sqlite3::memory:', auto_reconnect=value)
