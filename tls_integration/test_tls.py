"""Certificate and transport acceptance against actual disposable SQL servers."""
import os
from pathlib import Path
import unittest
from urllib.parse import urlencode
import uuid

import MySQLdb
import psycopg2
from sonicprobe.libs import anysql

TARGETS=(('postgresql',35432),('mysql',33306),('mariadb',33316))
ERRORS=(MySQLdb.Error,psycopg2.Error,ValueError)


class VerifiedSQLTLS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ['SONICPROBE_SQL_TLS_FIXTURES'])
        if not cls.root.is_absolute() or not (cls.root/'ca.pem').is_file():
            raise RuntimeError('Explicit disposable TLS fixture directory required')

    def uri(self, backend, port, *, host='sql-tls.test', ca='ca', mode='rw', client=False):
        query={'tls':'verify-full','tls_ca':str(self.root/(ca+'.pem')),'mode':mode}
        if client:query.update(tls_cert=str(self.root/'client.pem'),tls_key=str(self.root/'client.key'))
        scheme='postgresql' if backend=='postgresql' else 'mysql'
        user='tls_client' if client else 'anysql'
        return scheme+'://'+user+':synthetic-test-password@'+host+':'+str(port)+'/anysql_test?'+urlencode(query)

    def connect(self,*args,**kwargs):
        return anysql.connect_by_uri(self.uri(*args,**kwargs),auto_reconnect=False)

    def encrypted(self,connection,backend):
        if backend=='postgresql':self.assertTrue(connection.driver_connection.info.ssl_in_use)
        else:
            cursor=connection.cursor()
            try:
                cursor.query("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
                self.assertTrue(cursor.fetchone()[1])
            finally:cursor.close()

    def test_verified_connections_commit_rollback_and_reconnect(self):
        for backend,port in TARGETS:
            with self.subTest(backend=backend):
                connection=self.connect(backend,port)
                table='tls_'+uuid.uuid4().hex
                try:
                    self.encrypted(connection,backend)
                    cursor=connection.cursor()
                    cursor.query('CREATE TABLE '+table+' (id INTEGER PRIMARY KEY)');connection.commit()
                    cursor.query('INSERT INTO '+table+' VALUES(?)',parameters=(1,));connection.rollback()
                    cursor.query('SELECT COUNT(*) FROM '+table);self.assertEqual(cursor.fetchone()[0],0)
                    cursor.query('INSERT INTO '+table+' VALUES(?)',parameters=(2,));connection.commit()
                    cursor.close();connection.close();connection.reconnect()
                    self.encrypted(connection,backend)
                    cursor=connection.cursor()
                    cursor.query('SELECT id FROM '+table);self.assertEqual(cursor.fetchone()[0],2)
                    cursor.query('DROP TABLE '+table);connection.commit();cursor.close()
                finally:connection.close()

    def test_read_only_remains_read_only_over_verified_tls(self):
        for backend,port in TARGETS:
            with self.subTest(backend=backend):
                connection=self.connect(backend,port,mode='ro')
                try:
                    self.encrypted(connection,backend)
                    for reconnect in (False,True):
                        if reconnect:connection.close();connection.reconnect()
                        cursor=connection.cursor()
                        with self.assertRaises(ERRORS):cursor.query('CREATE TABLE forbidden_tls_write (id INTEGER PRIMARY KEY)')
                        connection.rollback();cursor.close()
                finally:connection.close()

    def test_untrusted_authority_is_rejected(self):
        for backend,port in TARGETS:
            with self.subTest(backend=backend),self.assertRaises(ERRORS):self.connect(backend,port,ca='wrong-ca')

    def test_wrong_hostname_is_rejected(self):
        for backend,port in TARGETS:
            with self.subTest(backend=backend),self.assertRaises(ERRORS):self.connect(backend,port,host='wrong.sql-tls.test')

    def test_expired_certificate_is_rejected(self):
        for backend,port in TARGETS:
            with self.subTest(backend=backend),self.assertRaises(ERRORS):self.connect(backend,port+2)

    def test_plaintext_server_is_rejected_without_downgrade(self):
        for backend,port in TARGETS:
            with self.subTest(backend=backend),self.assertRaises(ERRORS):self.connect(backend,port+1)

    def test_missing_ca_file_is_rejected(self):
        for backend,port in TARGETS:
            with self.subTest(backend=backend),self.assertRaises(ERRORS):self.connect(backend,port,ca='does-not-exist')

    def test_client_certificate_authentication_and_missing_certificate(self):
        for backend,port in TARGETS:
            with self.subTest(backend=backend):
                connection=self.connect(backend,port,client=True)
                try:
                    self.encrypted(connection,backend)
                    cursor=connection.cursor();cursor.query('SELECT 1');self.assertEqual(cursor.fetchone()[0],1);cursor.close()
                finally:connection.close()
                uri=self.uri(backend,port).replace('://anysql:', '://tls_client:')
                with self.assertRaises(ERRORS):anysql.connect_by_uri(uri,auto_reconnect=False)
