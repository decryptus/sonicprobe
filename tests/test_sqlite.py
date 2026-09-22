import unittest
from sonicprobe.libs.BackSQL import backsqlite3
from sonicprobe.libs import anysql

class SQLiteTests(unittest.TestCase):
    def test_timeout_is_milliseconds(self):
        conn = backsqlite3.connect_by_uri('sqlite3::memory:?timeout_ms=250')
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute('PRAGMA busy_timeout').fetchone()[0], 250)

    def test_identifier_escaping(self):
        self.assertEqual(backsqlite3.escape('table.na"me'), '"table"."na""me"')

    def test_connection_and_disconnection(self):
        conn = backsqlite3.connect_by_uri('sqlite3::memory:')
        self.assertTrue(backsqlite3.is_connected(conn))
        conn.close()
        self.assertFalse(backsqlite3.is_connected(conn))

    def test_constraint_error_does_not_reconnect_and_lose_transaction(self):
        import sqlite3
        conn = anysql.connect_by_uri('sqlite3::memory:')
        self.addCleanup(conn.close)
        cursor = conn.cursor()
        cursor.query('CREATE TABLE items (id INTEGER PRIMARY KEY)')
        cursor.query('INSERT INTO items VALUES (?)', None, [1])
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.query('INSERT INTO items VALUES (?)', None, [1])
        cursor.query('SELECT id FROM items')
        self.assertEqual(cursor.fetchone()[0], 1)
