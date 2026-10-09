"""Real, disposable SQL servers; all three explicitly configured targets required."""
import os
import unittest
import uuid

import MySQLdb
import psycopg2

from sonicprobe.libs import anysql
from sonicprobe.libs.urisup import AUTHORITY, PATH, uri_help_split, uri_help_unsplit

TARGETS = ('MYSQL', 'MARIADB', 'POSTGRESQL')
DATABASE_ERRORS = (MySQLdb.Error, psycopg2.Error)


class SQLAccessModes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.urls = {}
        for target in TARGETS:
            value = os.environ.get('SONICPROBE_' + target + '_TEST_URL')
            if not value:
                raise RuntimeError('All three disposable SQL test URLs are required')
            parts = uri_help_split(value)
            if (parts[AUTHORITY][2] != '127.0.0.1' or parts[PATH] != '/anysql_test'):
                raise RuntimeError('SQL acceptance requires the dedicated local test databases')
            cls.urls[target] = value

    def setUp(self):
        self.table = 'sp_mode_' + uuid.uuid4().hex
        for target in TARGETS:
            connection = self.connect(target)
            try:
                cursor = connection.cursor()
                cursor.query('CREATE TABLE ' + self.table + ' (id INTEGER PRIMARY KEY)')
                connection.commit()
                self.addCleanup(self.drop_table, target)
                cursor.query('INSERT INTO ' + self.table + ' VALUES (1)')
                connection.commit()
            finally:
                connection.close()

    def connect(self, target, mode=None):
        uri = self.urls[target]
        if mode is not None:
            uri += '?mode=' + mode
        return anysql.connect_by_uri(uri, auto_reconnect=False)

    def drop_table(self, target):
        connection = self.connect(target)
        try:
            connection.cursor().query('DROP TABLE ' + self.table)
            connection.commit()
        finally:
            connection.close()

    def ids(self, connection):
        cursor = connection.cursor()
        cursor.query('SELECT id FROM ' + self.table + ' ORDER BY id')
        return [row[0] for row in cursor.fetchall()]

    def test_default_and_rw_allow_writes_with_commit_and_rollback(self):
        for target in TARGETS:
            for mode in (None, 'rw'):
                with self.subTest(target=target, mode=mode):
                    connection = self.connect(target, mode)
                    try:
                        cursor = connection.cursor()
                        cursor.query('INSERT INTO ' + self.table + ' VALUES (2)')
                        connection.rollback()
                        self.assertEqual(self.ids(connection), [1])
                        cursor.query('INSERT INTO ' + self.table + ' VALUES (3)')
                        connection.commit()
                        self.assertEqual(self.ids(connection), [1, 3])
                        cursor.query('DELETE FROM ' + self.table + ' WHERE id = 3')
                        connection.commit()
                    finally:
                        connection.close()

    def test_ro_reads_and_refuses_regular_data_and_schema_writes(self):
        for target in TARGETS:
            with self.subTest(target=target):
                connection = self.connect(target, 'ro')
                try:
                    self.assertEqual(self.ids(connection), [1])
                    connection.commit()
                    for sql in ('INSERT INTO ' + self.table + ' VALUES (2)',
                                'UPDATE ' + self.table + ' SET id = 2',
                                'DELETE FROM ' + self.table,
                                'ALTER TABLE ' + self.table + ' ADD forbidden INTEGER'):
                        with self.assertRaises(DATABASE_ERRORS):
                            connection.cursor().query(sql)
                        connection.rollback()
                    self.assertEqual(self.ids(connection), [1])
                finally:
                    connection.close()

    def test_ro_survives_commit_rollback_and_reconnect(self):
        for target in TARGETS:
            with self.subTest(target=target):
                connection = self.connect(target, 'ro')
                try:
                    for boundary in (connection.commit, connection.rollback):
                        self.assertEqual(self.ids(connection), [1])
                        boundary()
                        with self.assertRaises(DATABASE_ERRORS):
                            connection.cursor().query('INSERT INTO ' + self.table + ' VALUES (2)')
                        connection.rollback()
                    connection.close()
                    connection.reconnect()
                    with self.assertRaises(DATABASE_ERRORS):
                        connection.cursor().query('INSERT INTO ' + self.table + ' VALUES (2)')
                    connection.rollback()
                finally:
                    connection.close()

    def test_rwc_alias_allows_writes(self):
        for target in TARGETS:
            with self.subTest(target=target):
                connection = self.connect(target, 'rwc')
                try:
                    connection.cursor().query('INSERT INTO ' + self.table + ' VALUES (2)')
                    connection.commit()
                    self.assertEqual(self.ids(connection), [1, 2])
                finally:
                    connection.close()

    def test_missing_server_database_is_not_created(self):
        for target in TARGETS:
            modes = ('ro', 'rw', 'rwc')
            for mode in modes:
                with self.subTest(target=target, mode=mode):
                    parts = list(uri_help_split(self.urls[target]))
                    parts[PATH] = '/sp_missing_' + uuid.uuid4().hex
                    with self.assertRaises(DATABASE_ERRORS):
                        anysql.connect_by_uri(uri_help_unsplit(parts) + '?mode=' + mode,
                                              auto_reconnect=False)
