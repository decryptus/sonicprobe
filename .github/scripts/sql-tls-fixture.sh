#!/usr/bin/env bash
# Disposable fixtures only; no real credentials, published ports bind loopback.
set -euo pipefail
operation="${1:?start or stop}"
if [[ "$operation" == stop ]]; then
  for backend in postgresql mysql mariadb; do
    for kind in tls plain expired; do
      name="anysql-$kind-$backend"
      if docker container inspect "$name" >/dev/null 2>&1; then docker rm -f "$name" >/dev/null; fi
    done
  done
  exit
fi
[[ "$operation" == start ]]
fixture_root="${2:?absolute fresh fixture directory}"
[[ "$fixture_root" == /* && ! -e "$fixture_root" ]]
python "$(dirname "$0")/make-sql-tls-certificates.py" "$fixture_root"
# Trusted test DNS names resolve only to these local, disposable servers.
echo '127.0.0.1 sql-tls.test wrong.sql-tls.test' | sudo tee -a /etc/hosts >/dev/null
for backend in postgresql mysql mariadb; do
  for kind in tls plain expired; do
    case "$backend" in
      postgresql) image=postgres:16; internal=5432; base=35432; user=postgres ;;
      mysql) image=mysql:8.4; internal=3306; base=33306; user=mysql ;;
      mariadb) image=mariadb:11.4; internal=3306; base=33316; user=mysql ;;
    esac
    case "$kind" in tls) port="$base"; cert=server ;; plain) port=$((base+1)); cert=server ;; expired) port=$((base+2)); cert=expired ;; esac
    name="anysql-$kind-$backend"
    # Do not replace existing containers. A name collision must fail.
    if [[ "$backend" == postgresql ]]; then
      args=(postgres -c ssl=on -c ssl_ca_file=/certs/ca.pem -c ssl_cert_file=/certs/server.pem -c ssl_key_file=/certs/server.key)
      if [[ "$kind" == plain ]]; then args=(postgres -c ssl=off); fi
      env_args=(-e POSTGRES_DB=anysql_test -e POSTGRES_USER=anysql -e POSTGRES_PASSWORD=synthetic-test-password)
    else
      daemon=mysqld
      if [[ "$backend" == mariadb ]]; then daemon=mariadbd; fi
      args=("$daemon" --ssl-ca=/certs/ca.pem --ssl-cert=/certs/server.pem --ssl-key=/certs/server.key)
      if [[ "$kind" == plain ]]; then
        if [[ "$backend" == mysql ]]; then args=(mysqld --tls-version=); else args=(mariadbd --skip-ssl); fi
      fi
      env_args=(-e MYSQL_DATABASE=anysql_test -e MYSQL_ROOT_PASSWORD=synthetic-test-password -e MYSQL_ROOT_HOST=% -e MYSQL_USER=anysql -e MYSQL_PASSWORD=synthetic-test-password)
    fi
    docker run -d --name "$name" -p "127.0.0.1:$port:$internal" "${env_args[@]}" \
      -v "$fixture_root:/tls:ro" --entrypoint bash "$image" -c \
      'mkdir -p /certs; cp /tls/ca.pem /certs/ca.pem; cp "/tls/$1.pem" /certs/server.pem; cp "/tls/$1.key" /certs/server.key; chown -R "$2:$2" /certs; chmod 600 /certs/*.key; shift 2; exec docker-entrypoint.sh "$@"' \
      fixture "$cert" "$user" "${args[@]}" >/dev/null
  done
 done
python "$(dirname "$0")/sql-tls-ready.py" "$fixture_root"
