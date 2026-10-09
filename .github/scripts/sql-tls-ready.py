"""Wait for synthetic servers over local container sockets, then add mTLS users."""
import subprocess
import time

for backend in ('postgresql','mysql','mariadb'):
    for kind in ('tls','plain','expired'):
        container='anysql-'+kind+'-'+backend
        if backend=='postgresql':
            command=['docker','exec','-u','postgres',container,'psql','-U','anysql','-d','anysql_test','-v','ON_ERROR_STOP=1','-At','-c']
        else:
            command=['docker','exec',container,'mysql' if backend=='mysql' else 'mariadb',
                     '--protocol=socket','-uroot','-psynthetic-test-password','--batch','--skip-column-names','-e']
        deadline=time.monotonic()+150
        while True:
            # Image entrypoints run a temporary socket-only server during bootstrap.
            # Wait for the final TCP-enabled server before creating fixture users.
            probe = "SELECT current_setting('listen_addresses')" if backend=='postgresql' else 'SELECT @@skip_networking'
            result=subprocess.run(command+[probe],capture_output=True)
            expected=b'*' if backend=='postgresql' else b'0'
            if result.returncode==0 and result.stdout.strip()==expected:break
            if time.monotonic()>deadline:
                subprocess.run(['docker','logs',container],check=False)
                raise RuntimeError('Disposable SQL server failed to start: '+backend+' '+kind)
            time.sleep(1)
        if kind=='tls':
            if backend=='postgresql':
                sql="CREATE ROLE tls_client LOGIN PASSWORD 'synthetic-test-password'"
            else:
                sql="CREATE USER 'tls_client'@'%' IDENTIFIED BY 'synthetic-test-password' REQUIRE X509; GRANT SELECT ON anysql_test.* TO 'tls_client'@'%'; GRANT ALL PRIVILEGES ON *.* TO 'anysql'@'%'"
            subprocess.run(command+[sql],check=True)
            if backend=='postgresql':
                subprocess.run(['docker','exec','-u','postgres',container,'bash','-c',
                    '''sed -i '1i hostssl all tls_client all scram-sha-256 clientcert=verify-full' "$PGDATA/pg_hba.conf"; pg_ctl reload -D "$PGDATA"'''],check=True)
print('All nine disposable SQL TLS/plain/expired fixtures are ready')
