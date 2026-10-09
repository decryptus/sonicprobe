# SQL TLS adapter validation

The URI parser lives in the generic `sqltls` helper; PostgreSQL and MySQL/MariaDB
translate it into their own driver options. No TLS keys means no new driver
parameters or session checks. Explicit TLS requires a CA and verified identity;
it rejects native SSL/socket/option-file overrides. MySQL additionally refuses
its special localhost socket route. Connections are closed if TLS was requested
but the returned session is not encrypted.

The optional-driver unit contracts verify parameter mapping, paired client
credentials, rejection before connect, cleanup and failure without fallback.
The normal interpreter and consumer matrices remain in force. The new
`tls_integration` suite runs the installed package against PostgreSQL 16,
MySQL 8.4 and MariaDB 11.4 with generated, short-lived synthetic certificates.
It exercises positive TLS, transactions, explicit reconnect, persistent RO,
wrong CA, wrong host, expired certificates, absent CA files, plaintext servers,
and mutual TLS with and without the required client certificate.

`.github/scripts/sql-tls-fixture.sh` provisions nine disposable Docker containers
bound only to loopback: valid TLS, expired TLS and plaintext for each engine.
It never replaces an existing container. The helper generates no production key
material and requires a fresh directory. The stop command removes only those
fixture containers. Database administration uses container-local sockets;
acceptance connections use TCP DNS identities mapped to loopback.

Run collection with `.github/scripts/check-test-collection.py --runner unittest
 tls_integration` and then unittest discovery, with `SONICPROBE_SQL_TLS_FIXTURES`
set to that generated directory. Missing fixtures or driver dependencies fail
rather than skip. Actual acceptance results are recorded in the change's CI.
