"""Driver doubles test parameter and cleanup contracts, not live databases."""
import importlib
import sys
import types
import unittest
try:
    from unittest import mock
except ImportError:
    import mock
from sonicprobe.libs import anysql


class SQLDriverContracts(unittest.TestCase):
    def setUp(self):
        self.saved_registry = anysql.__dict__['__uri_create_methods'].copy()
        self.addCleanup(self.restore_registry)

    def restore_registry(self):
        registry = anysql.__dict__['__uri_create_methods']
        registry.clear(); registry.update(self.saved_registry)

    def load_backend(self, backend, modules):
        name = 'sonicprobe.libs.BackSQL.back' + backend
        # Do not let optional driver doubles leak into other tests or consumers.
        previous = sys.modules.pop(name, None)
        try:
            with mock.patch.dict(sys.modules, modules):
                module = importlib.import_module(name)
        finally:
            sys.modules.pop(name, None)
            if previous is not None:
                sys.modules[name] = previous
        return module

    def mysql(self):
        driver = types.ModuleType('MySQLdb')
        driver.apilevel, driver.paramstyle, driver.threadsafety = '2.0', 'format', 1
        driver.connect = mock.Mock()
        driver.cursors = types.ModuleType('MySQLdb.cursors')
        conversions = types.ModuleType('MySQLdb.converters')
        conversions.conversions = {1: ['original']}
        backend = self.load_backend('mysql', {'MySQLdb': driver, 'MySQLdb.cursors': driver.cursors,
                                              'MySQLdb.converters': conversions})
        return backend, driver, conversions

    def test_mysql_session_values_use_parameters_and_false_compression(self):
        backend, driver, _ = self.mysql()
        conn = backend.connect_by_uri('mysql://user:pass@localhost/db?time_zone=%2B00%3A00&compress=0')
        self.assertFalse(driver.connect.call_args[1]['compress'])
        conn.cursor.return_value.execute.assert_called_once_with('SET @@session.time_zone = %s', ('+00:00',))
        conn.cursor.return_value.close.assert_called_once_with()

    def test_mysql_setup_failure_closes_connection(self):
        backend, driver, _ = self.mysql()
        conn = driver.connect.return_value
        conn.cursor.return_value.execute.side_effect = ValueError('driver failed')
        with self.assertRaises(ValueError):
            backend.connect_by_uri('mysql://localhost/db?autocommit=1')
        conn.close.assert_called_once_with()
        conn.cursor.return_value.close.assert_called_once_with()

    def test_mysql_conversion_lists_are_not_shared(self):
        backend, driver, conversions = self.mysql()
        backend.connect_by_uri('mysql://localhost/db')
        driver.connect.call_args[1]['conv'][1].append('added')
        self.assertEqual(conversions.conversions[1], ['original'])

    def test_postgres_identifier_quotes_are_doubled(self):
        driver = types.ModuleType('psycopg2')
        driver.apilevel, driver.paramstyle, driver.threadsafety = '2.0', 'pyformat', 2
        driver.extensions = mock.Mock()
        backend = self.load_backend('postgresql', {'psycopg2': driver, 'psycopg2.extensions': driver.extensions})
        self.assertEqual(backend.escape('schema.a"b'), '"schema"."a""b"')
