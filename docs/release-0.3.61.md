# Sonicprobe 0.3.61

The PostgreSQL AnySQL adapter now accepts an explicit positive integer
`connect_timeout` URI parameter and forwards it to libpq. Invalid values are
rejected before opening a connection. The adapter advertises this capability so
callers can check support instead of silently assuming their budget is enforced.

Without this parameter, the existing driver behavior is preserved. Read-only,
read-write and verified TLS settings retain their existing semantics. The driver
connect timeout is not a total query deadline or a retry policy.

See [SQL access modes](sql-access-modes.md) for configuration. Install with
`python -m pip install --upgrade 'sonicprobe==0.3.61'`.

The release adds validation cases and an installed-driver test against a local
PostgreSQL peer that accepts the connection but stalls during startup. The
supported Python interpreter matrix is unchanged.
