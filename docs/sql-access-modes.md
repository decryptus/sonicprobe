# SQL connection access modes

AnySQL accepts an optional `mode` URI parameter. Omitting it preserves the
historical backend behavior and driver call.

| Backend | `ro` | `rw` | `rwc` |
| --- | --- | --- | --- |
| SQLite (`sqlite3:`) | Existing file, read only | Existing file, read/write | Read/write, create file if absent |
| MySQL / MariaDB (`mysql:`) | Read-only transactions | Read/write transactions | Alias of `rw`; never creates a database |
| PostgreSQL (`postgresql:`) | Read-only transactions | Read/write transactions | Alias of `rw`; never creates a database |

Empty, duplicate and unknown modes are rejected before connecting. An explicit
mode never falls back to the default after failure. SQLite file modes require
Python 3.4+ and SQLite 3.7.7+; older supported runtimes retain the mode-free API
and explicitly reject file modes. File paths are encoded before constructing
SQLite's URI, including literal question marks, percent signs and hashes.

```python
from sonicprobe.libs import anysql

connection = anysql.connect_by_uri(
    'sqlite3:///private/accounts.db?mode=ro', auto_reconnect=False)
try:
    cursor = connection.cursor()
    cursor.query('SELECT id FROM users WHERE enabled = ?', parameters=[1])
    rows = cursor.fetchall()
finally:
    connection.close()
```

For caller-owned transactions, `auto_reconnect=False` prevents automatic query
replay or reconnection after query, fetch or commit errors. It does not change
transaction isolation or autocommit.

On MySQL/MariaDB the adapter configures the session transaction access mode.
PostgreSQL applies `default_transaction_read_only` at connection establishment.
These defaults survive commit/rollback and are reapplied on an explicit
reconnect. They are **not database privileges**: a caller with sufficient
permissions can change its session settings. Use a database account with
read-only grants when access must remain restricted independently of the caller.
SQLite `ro` prevents persistent writes to the opened database file; it does not
restrict access to other files that arbitrary application code can open.

## Backend-specific adapters

`connection.driver_connection` exposes the underlying DBAPI connection for
backend-specific operations (SQLite pragmas, trace callbacks and transaction
configuration). Its lifetime belongs to the AnySQL connection. Driver calls do
not perform AnySQL reconnection or replay; they are not portable across drivers.

With an explicit SQLite file mode, `check_same_thread=false` may be supplied by
an adapter that serializes access itself. Accepted values are `true` and `false`;
duplicates are rejected. The default thread check remains enabled. Never share
an unprotected connection between workers.
