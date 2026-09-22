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
