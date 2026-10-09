"""Wait for synthetic servers over local container sockets, then add mTLS users."""
import subprocess
import time

for backend in ('postgresql','mysql','mariadb'):
    for kind in ('tls','plain','expired'):
        container='anysql-'+kind+'-'+backend
        if backend=='postgresql':
            command=['docker','exec','-u','postgres',container,'psql','-U','anysql','-d','anysql_test','-v','ON_ERROR_STOP=1','-c']
        else:
            command=['docker','exec',container,'mysql' if backend=='mysql' else 'mariadb',
                     '--protocol=socket','-uroot','-psynthetic-test-password','-e']
        deadline=time.monotonic()+150
        while True:
            result=subprocess.run(command+['SELECT 1'],capture_output=True)
            if result.returncode==0:break
            if time.monotonic()>deadline:
                subprocess.run(['docker','logs',container],check=False)
                raise RuntimeError('Disposable SQL server failed to start: '+backend+' '+kind)
            time.sleep(1)
        if kind=='tls':
            if backend=='postgresql':
                sql="CREATE ROLE tls_client LOGIN PASSWORD 'synthetic-test-password'"
            else:
                sql="CREATE USER 'tls_client'@'%' IDENTIFIED BY 'synthetic-test-password' REQUIRE X509; GRANT SELECT ON anysql_test.* TO 'tls_client'@'%'; GRANT ALL PRIVILEGES ON *.* TO 'anysql'@'%'"
            subprocess.run(command+[sql],check=True,capture_output=True)
            if backend=='postgresql':
                subprocess.run(['docker','exec','-u','postgres',container,'bash','-c',
                    '''sed -i '1i hostssl all tls_client all scram-sha-256 clientcert=verify-full' "$PGDATA/pg_hba.conf"; pg_ctl reload -D "$PGDATA"'''],check=True)
print('All nine disposable SQL TLS/plain/expired fixtures are ready')
