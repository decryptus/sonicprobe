# Verified SQL TLS

AnySQL's PostgreSQL and MySQL/MariaDB adapters accept the same explicit TLS
parameters from version 0.3.60. With no `tls` parameters, existing driver behavior
is unchanged. To require encryption, a trusted certificate and a matching server
name, use:

```python
from sonicprobe.libs import anysql

connection = anysql.connect_by_uri(
    'postgresql://account:password@db.example.net/database'
    '?mode=rw&tls=verify-full&tls_ca=%2Fetc%2Fapp%2Fdatabase-ca.pem',
    auto_reconnect=False)
```

Use the `mysql://` scheme for MySQL or MariaDB. Percent-encode credentials and
query parameter values. Keep credentials in private configuration, not logs.

| Parameter | Meaning |
| --- | --- |
| `tls=verify-full` | Require TLS, validate the certificate chain and server identity |
| `tls_ca` | PEM certificate-authority bundle used to trust the server; required |
| `tls_cert` | Optional PEM client certificate/chain for mutual TLS |
| `tls_key` | Matching private key; required together with `tls_cert` |

Use absolute file paths in services. Keep client private keys restricted to the
service account (0600; PostgreSQL/libpq also enforces private-key permissions).
Configure server-side client-certificate authentication when using mutual TLS.
The host in the URL must match the server certificate's DNS name or IP SAN.
MySQL's special `localhost` socket route is rejected when TLS is explicit: use a
DNS name or an IP address to request a TCP connection and match its certificate.
Unix-socket overrides and option files cannot be combined with explicit TLS.

The only explicit TLS mode is `verify-full`. Empty/duplicate/unknown TLS options,
a missing CA, incomplete client certificate/key pairs, and competing native
`ssl*` options are rejected. A certificate or handshake failure propagates; the
adapter does not retry with weaker settings. Both adapters also check that the
resulting session actually negotiated TLS before returning it to the caller.
Automatic query replay is a separate setting; use `auto_reconnect=False` for
transactions that your application controls.

PostgreSQL maps this configuration to libpq `sslmode=verify-full` and
`sslrootcert`. MySQL/MariaDB map it to mysqlclient's `ssl_mode=VERIFY_IDENTITY`
and SSL certificate options. Drivers must support these capabilities; unsupported
options fail instead of being dropped. Actual TLS acceptance uses psycopg2 2.9+
and mysqlclient 2.2.4+ on Python 3.12. Sonicprobe's mode-free APIs and supported
legacy interpreters keep their existing behavior.

TLS can be combined with `mode=ro`, `rw` or `rwc`; explicit reconnects reapply both
TLS and access-mode settings. Read-only mode is still a transaction default, not
a replacement for database grants. See [SQL access modes](sql-access-modes.md).
