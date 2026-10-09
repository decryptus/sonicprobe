"""Opt-in SQLite file modes, with the historical default preserved."""
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
from sonicprobe.libs.BackSQL import backsqlite3
from sonicprobe.libs.urisup import uri_help_unsplit


class SQLiteModeTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = os.path.join(self.root, 'accounts.db')

    def uri(self, mode=None, path=None, extra=()):
        query = list(extra)
        if mode is not None:
            query.append(('mode', mode))
        return uri_help_unsplit(('sqlite3', None, path or self.path, query, None))

    def seed(self, path=None):
        connection = sqlite3.connect(path or self.path)
        try:
            connection.execute('CREATE TABLE items (id INTEGER PRIMARY KEY)')
            connection.execute('INSERT INTO items VALUES (1)')
            connection.commit()
        finally:
            connection.close()

    def test_default_creates_and_reopens_writable_database(self):
        connection = backsqlite3.connect_by_uri(self.uri())
        connection.execute('CREATE TABLE items (id INTEGER PRIMARY KEY)')
        connection.execute('INSERT INTO items VALUES (1)')
        connection.commit()
        connection.close()
        connection = backsqlite3.connect_by_uri(self.uri())
        self.addCleanup(connection.close)
        connection.execute('INSERT INTO items VALUES (2)')
        self.assertEqual(connection.execute('SELECT count(*) FROM items').fetchone()[0], 2)

    def test_default_keeps_original_driver_call_and_ignored_options(self):
        with mock.patch.object(backsqlite3.sqlite3, 'connect') as connect:
            backsqlite3.connect_by_uri(self.uri(extra=(('unrecognized', 'unchanged'),)))
            connect.assert_called_once_with(self.path)
        with mock.patch.object(backsqlite3.sqlite3, 'connect') as connect:
            backsqlite3.connect_by_uri('sqlite3::memory:?timeout_ms=250')
            connect.assert_called_once_with(':memory:', 0.25)

    def test_invalid_and_duplicate_modes_fail_before_opening(self):
        for query in ((('mode', ''),), (('mode', 'memory'),), (('mode', 'RO'),),
                      (('mode', 'ro'), ('mode', 'rw'))):
            with mock.patch.object(backsqlite3.sqlite3, 'connect') as connect:
                with self.assertRaises(ValueError):
                    backsqlite3.connect_by_uri(self.uri(extra=query))
                self.assertFalse(connect.called)
        self.assertFalse(os.path.exists(self.path))

    def test_explicit_file_modes_reject_memory_and_empty_path(self):
        for uri in ('sqlite3::memory:?mode=rw', 'sqlite3:?mode=rwc'):
            with self.assertRaises(ValueError):
                backsqlite3.connect_by_uri(uri)

    def test_unsupported_runtime_never_falls_back_to_creation(self):
        with mock.patch.object(backsqlite3, 'URI_MODES_SUPPORTED', False):
            with self.assertRaises(NotImplementedError):
                backsqlite3.connect_by_uri(self.uri('rw'))
        self.assertFalse(os.path.exists(self.path))

    @unittest.skipUnless(backsqlite3.URI_MODES_SUPPORTED, 'Explicit URI modes require Python 3.4+ and SQLite 3.7.7+')
    def test_existing_only_modes_do_not_create_missing_database(self):
        for mode in ('ro', 'rw'):
            with self.assertRaises(sqlite3.OperationalError):
                backsqlite3.connect_by_uri(self.uri(mode))
            self.assertFalse(os.path.exists(self.path))

    @unittest.skipUnless(backsqlite3.URI_MODES_SUPPORTED, 'Explicit URI modes require Python 3.4+ and SQLite 3.7.7+')
    def test_rw_supports_commit_rollback_and_reopen_through_anysql(self):
        self.seed()
        connection = anysql.connect_by_uri(self.uri('rw'), auto_reconnect=False)
        try:
            cursor = connection.cursor()
            cursor.query('INSERT INTO items VALUES (?)', None, [2])
            connection.rollback()
            cursor.query('INSERT INTO items VALUES (?)', None, [3])
            connection.commit()
        finally:
            connection.close()
        connection = anysql.connect_by_uri(self.uri('ro'), auto_reconnect=False)
        self.addCleanup(connection.close)
        cursor = connection.cursor()
        cursor.query('SELECT id FROM items ORDER BY id')
        self.assertEqual([row[0] for row in cursor.fetchall()], [1, 3])

    @unittest.skipUnless(backsqlite3.URI_MODES_SUPPORTED, 'Explicit URI modes require Python 3.4+ and SQLite 3.7.7+')
    def test_ro_reads_but_refuses_data_and_schema_writes(self):
        self.seed()
        connection = anysql.connect_by_uri(self.uri('ro'), auto_reconnect=False)
        self.addCleanup(connection.close)
        cursor = connection.cursor()
        cursor.query('SELECT id FROM items')
        self.assertEqual(cursor.fetchone()[0], 1)
        for statement in ('INSERT INTO items VALUES (2)', 'CREATE TABLE forbidden (id INTEGER)'):
            with self.assertRaises(sqlite3.OperationalError):
                cursor.query(statement)

    @unittest.skipUnless(backsqlite3.URI_MODES_SUPPORTED, 'Explicit URI modes require Python 3.4+ and SQLite 3.7.7+')
    def test_rwc_explicitly_creates_and_preserves_existing_data(self):
        connection = backsqlite3.connect_by_uri(self.uri('rwc'))
        connection.execute('CREATE TABLE items (id INTEGER PRIMARY KEY)')
        connection.execute('INSERT INTO items VALUES (1)')
        connection.commit()
        connection.close()
        connection = backsqlite3.connect_by_uri(self.uri('rwc'))
        self.addCleanup(connection.close)
        self.assertEqual(connection.execute('SELECT id FROM items').fetchone()[0], 1)

    @unittest.skipUnless(backsqlite3.URI_MODES_SUPPORTED, 'Explicit URI modes require Python 3.4+ and SQLite 3.7.7+')
    def test_encoded_and_relative_paths_and_canonicalization_preserve_mode(self):
        path = os.path.join(self.root, u'caf\u00e9 space %23 ?mode=rwc #.db')
        self.seed(path)
        relative = os.path.relpath(path)
        uri = self.uri('ro', path=relative)
        for value in (uri, anysql.c14n_uri(uri)):
            connection = backsqlite3.connect_by_uri(value)
            try:
                self.assertEqual(connection.execute('SELECT id FROM items').fetchone()[0], 1)
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute('INSERT INTO items VALUES (2)')
            finally:
                connection.close()
        self.assertEqual(os.listdir(self.root), [os.path.basename(path)])

    @unittest.skipUnless(backsqlite3.URI_MODES_SUPPORTED, 'Explicit URI modes require Python 3.4+ and SQLite 3.7.7+')
    def test_timeout_and_writer_contention_remain_effective(self):
        self.seed()
        first = backsqlite3.connect_by_uri(self.uri('rw'))
        self.addCleanup(first.close)
        second = backsqlite3.connect_by_uri(self.uri('rw', extra=(('timeout_ms', '1'),)))
        self.addCleanup(second.close)
        self.assertEqual(second.execute('PRAGMA busy_timeout').fetchone()[0], 1)
        first.execute('BEGIN IMMEDIATE')
        with self.assertRaises(sqlite3.OperationalError):
            second.execute('BEGIN IMMEDIATE')
        first.rollback()
        second.execute('BEGIN IMMEDIATE')
        second.rollback()

    @unittest.skipUnless(backsqlite3.URI_MODES_SUPPORTED, 'Explicit URI modes require Python 3.4+ and SQLite 3.7.7+')
    def test_disappeared_database_is_not_recreated_on_explicit_reconnect(self):
        self.seed()
        connection = anysql.connect_by_uri(self.uri('rw'), auto_reconnect=False)
        connection.close()
        os.unlink(self.path)
        with self.assertRaises(sqlite3.OperationalError):
            connection.reconnect()
        self.assertFalse(os.path.exists(self.path))

    @unittest.skipUnless(backsqlite3.URI_MODES_SUPPORTED, 'Explicit URI modes require Python 3.4+')
    def test_explicit_thread_option_and_driver_connection(self):
        import threading
        self.seed()
        connection = anysql.connect_by_uri(self.uri('rw', extra=(('check_same_thread', 'false'),)), auto_reconnect=False)
        self.addCleanup(connection.close)
        values = []
        def read():
            values.append(connection.driver_connection.execute('SELECT id FROM items').fetchone()[0])
        thread = threading.Thread(target=read)
        thread.start()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(values, [1])
        for options in ((('check_same_thread', 'maybe'),), (('check_same_thread', 'true'), ('check_same_thread', 'false'))):
            with self.assertRaises(ValueError):
                anysql.connect_by_uri(self.uri('rw', extra=options))
