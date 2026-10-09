# Sonicprobe 0.3.60

AnySQL now supports explicit, verified TLS on PostgreSQL and MySQL/MariaDB using
`tls=verify-full` and a `tls_ca` certificate-authority file. Optional `tls_cert`
and `tls_key` parameters support client-certificate authentication.

Explicit TLS verifies the certificate chain and server name. Invalid or competing
TLS parameters are rejected; certificate/handshake failures never trigger a weaker
connection attempt. Existing connections without these TLS options keep their
previous behavior, including default access modes and automatic-reconnect policy.

See [verified SQL TLS](sql-tls.md) for configuration and driver requirements.
