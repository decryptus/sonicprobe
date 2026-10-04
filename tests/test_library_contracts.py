# -*- coding: utf-8 -*-
"""Regression contracts for utility parsing and resource boundaries."""
import io
import os
import shutil
import tempfile
import unittest
from xml.parsers import expat
try:
    from unittest import mock
except ImportError:
    import mock
from sonicprobe.libs import anysql, daemonize, gencert, mysql_config_parser, urisup, xml2dict


class XMLContracts(unittest.TestCase):
    def test_incomplete_documents_are_rejected(self):
        for data in ('', '<root>', '<root><child/>', '<root>text', '<root/><!--'):
            with self.assertRaises(expat.ExpatError):
                xml2dict.Parse(data)

    def test_attributes_repeated_children_and_mixed_text(self):
        self.assertEqual(xml2dict.Parse('<root id="7">start<x>a</x><x>b</x>end</root>'),
                         {'root': {'id': '7', 'x': ['a', 'b'], '__cdata__': 'startend'}})

    def test_parser_can_be_reused_after_error(self):
        parser = xml2dict.XML2Dict()
        with self.assertRaises(expat.ExpatError):
            parser.Parse('<root>')
        self.assertEqual(parser.Parse(b'<root/>'), {'root': ''})


class URIContracts(unittest.TestCase):
    def test_scheme_predicate_rejects_empty_and_wrong_types(self):
        for value in ('', None, 3, [], '9abc', 'abc\n'):
            self.assertFalse(urisup.valid_scheme(value))
        self.assertTrue(urisup.valid_scheme('git+ssh'))

    def test_newline_in_fragment_is_not_silently_discarded(self):
        for newline in ('\n', '\r', '\r\n'):
            uri = 'https://example.org/#ok' + newline + 'suffix'
            self.assertEqual(urisup.basic_urisplit(uri)[4], 'ok' + newline + 'suffix')
            with self.assertRaises(urisup.InvalidFragmentError):
                urisup.uri_help_split(uri)

    def test_zero_query_values_survive_encoding(self):
        uri = urisup.uri_help_unsplit(('http', (None, None, 'example.org', 0), '/', ((0, 0), ('n', 0)), None))
        self.assertEqual(uri, 'http://example.org:0/?0=0&n=0')

    def test_existing_query_and_percent_contracts(self):
        value = 'https://user:pass@example.org/a%20b?x=a+b&x=%2B&flag#part'
        tree = urisup.uri_help_split(value)
        self.assertEqual(tree[3], (('x', 'a b'), ('x', '+'), ('flag', None)))
        self.assertEqual(urisup.uri_help_unsplit(tree), value)
        self.assertEqual(urisup.pct_decode('%zz'), '%zz')


class MySQLConfigurationContracts(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)

    def write_config(self, name, text):
        path = os.path.join(self.root, name)
        with io.open(path, 'w', encoding='utf8') as stream:
            stream.write(text)
        return path

    def test_readfp_remains_available(self):
        parser = mysql_config_parser.MySQLConfigParser()
        parser.readfp(io.StringIO(u'[client]\nuser=example\nflag\n'))
        self.assertEqual(parser.get('client', 'user'), 'example')
        self.assertIsNone(parser.get('client', 'flag'))

    def test_read_includes_files_and_directories(self):
        directory = os.path.join(self.root, 'included'); os.mkdir(directory)
        with io.open(os.path.join(directory, 'extra.cnf'), 'w') as stream:
            stream.write(u'[extra]\nanswer=42\n')
        child = self.write_config('child.cnf', u'[child]\nvalue=ok\n')
        main = self.write_config('main.cnf', u'!include %s\n!includedir %s\n' % (child, directory))
        parser = mysql_config_parser.MySQLConfigParser()
        self.assertEqual(parser.read(main), [main])
        self.assertEqual(parser.get('extra', 'answer'), '42')
        self.assertEqual(parser.get('child', 'value'), 'ok')

    def test_cyclic_includes_fail_explicitly(self):
        first = os.path.join(self.root, 'first.cnf')
        second = self.write_config('second.cnf', u'!include %s\n' % first)
        self.write_config('first.cnf', u'!include %s\n' % second)
        parser = mysql_config_parser.MySQLConfigParser()
        with self.assertRaises(mysql_config_parser.ParsingError):
            parser.read(first)

    def test_repeated_nonrecursive_include_and_missing_files(self):
        child = self.write_config('empty.cnf', u'# comment\n')
        main = self.write_config('main.cnf', u'!include %s\n!include %s\n[client]\na=1\n' % (child, child))
        parser = mysql_config_parser.MySQLConfigParser()
        self.assertEqual(parser.read([os.path.join(self.root, 'missing.cnf'), main]), [main])
        self.assertEqual(parser.get('client', 'a'), '1')

    def test_version_output_bytes_and_zero_components(self):
        self.write_config('client.cnf', u'[client]\nuser=base\n[client=dist-8.0.1]\nuser=version\n')
        loader = mysql_config_parser.MySQLConfigVersion(config_dir=self.root)
        with mock.patch.object(mysql_config_parser.subprocess, 'check_output',
                               return_value=b'mysql  Ver 14.14 Distrib 8.0.1, for Linux'):
            parser = loader.get_client()
        self.assertEqual(parser.get('client', 'user'), 'version')

    def test_custom_overrides_and_reload_drops_removed_options(self):
        self.write_config('client.cnf', u'[client]\nuser=base\n')
        self.write_config('custom.cnf', u'[client]\nuser=custom\nport=3307\n')
        loader = mysql_config_parser.MySQLConfigVersion(custom_file='custom.cnf', config_dir=self.root)
        self.assertEqual(loader.get_client(False).get('client', 'user'), 'custom')
        self.write_config('custom.cnf', u'[client]\nuser=new\n')
        parser = loader.get_client(False)
        self.assertEqual(parser.get('client', 'user'), 'new')
        self.assertFalse(parser.has_option('client', 'port'))

    def test_config_filename_must_match_completely(self):
        self.assertTrue(mysql_config_parser.MySQLConfigParser.valid_filename('client.cnf'))
        self.assertFalse(mysql_config_parser.MySQLConfigParser.valid_filename('client.cnf\n'))


class SQLContracts(unittest.TestCase):
    def test_rows_keep_list_slicing_and_named_access(self):
        row = anysql.cursor.row({'a': 0, 'b': 1}, [10, 20])
        self.assertEqual(row[:1], [10])
        self.assertEqual(row[-1], 20)
        self.assertEqual(row['a'], 10)

    def test_missing_dbapi_metadata_is_rejected_explicitly(self):
        with self.assertRaises(NotImplementedError):
            anysql.register_uri_backend('test', None, object(), None, None, None, None)

    def test_healthy_fetch_failure_does_not_replace_connection(self):
        for name in ('fetchone', 'fetchmany', 'fetchall'):
            conn = mock.Mock(auto_reconnect=True)
            conn.is_connected.return_value = True
            getattr(conn._get_raw_cursor.return_value, name).side_effect = ValueError('bad cursor')
            cursor = anysql.cursor(conn, [])
            with self.assertRaises(ValueError):
                getattr(cursor, name)()
            conn.reconnect.assert_not_called()

    def test_reconnect_logs_do_not_contain_uri_credentials_or_query(self):
        conn = anysql.connect_by_uri('sqlite3::memory:')
        self.addCleanup(conn.close)
        conn.sqluri = 'mysql://user:secret@localhost/db?passwd=othersecret'
        with mock.patch.object(conn, '_connection__connect'), mock.patch.object(anysql.LOG, 'warning') as log:
            conn.reconnect("INSERT INTO users VALUES ('private')", True)
        self.assertEqual(log.call_args[0], ('reconnecting to database (backend: %s)', 'mysql'))


class ResourceContracts(unittest.TestCase):
    def test_explicit_zero_certificate_days_are_preserved(self):
        self.assertEqual(gencert.GenCert(notafter_days=0).notafter_days, 0)

    def test_daemon_redirection_closes_extra_descriptor(self):
        with mock.patch.object(daemonize.os, 'fork', return_value=0), \
             mock.patch.object(daemonize.os, 'setsid'), \
             mock.patch.object(daemonize.os, 'umask'), \
             mock.patch.object(daemonize.os, 'chdir'), \
             mock.patch.object(daemonize.os, 'open', return_value=17), \
             mock.patch.object(daemonize.os, 'dup2'), \
             mock.patch.object(daemonize.os, 'close') as close:
            daemonize.daemonize()
        close.assert_called_once_with(17)
