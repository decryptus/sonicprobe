# SQLite transactions and read snapshots

`sonicprobe.libs.sqlite_transactions.SQLiteTransactions` provides explicit
transaction boundaries for an AnySQL SQLite connection. Use one instance per
connection, with automatic reconnection disabled and driver-managed implicit
transactions disabled:

```python
from sonicprobe.libs import anysql
from sonicprobe.libs.sqlite_transactions import SQLiteTransactions

connection = anysql.connect_by_uri('sqlite3:/private/state.db', auto_reconnect=False)
driver = connection.driver_connection
driver.isolation_level = None
driver.execute('PRAGMA journal_mode=WAL')
transactions = SQLiteTransactions(connection)

with transactions.transaction():
    driver.execute('INSERT INTO items (id) VALUES (?)', (1,))

with transactions.read_snapshot():
    rows = driver.execute('SELECT id FROM items').fetchall()

connection.close()
```

Create your application's tables before running this example. The helper does
not configure journal mode, timeouts, file access modes or schema. An existing
WAL database can be opened and read without reserving its writer.

`transaction()` uses `BEGIN IMMEDIATE`; `read_snapshot()` uses deferred `BEGIN`.
In WAL mode, a snapshot sees the committed state at its first database read
while another connection can continue writing. Commit happens once on success;
an exception rolls back without reconnecting, retrying or replaying statements.
If rollback fails, the original error is preserved and the helper refuses
further transactions; discard that connection.

Nested contexts join the outer transaction; they are not savepoints. A managed
write inside an outer read snapshot raises `ValueError`. Reads nested inside a
write transaction retain the outer write transaction. If a nested exception is
caught inside the outer body, the outer transaction still controls commit.

A snapshot is **not SQL write protection**: direct statements can still write.
Connection-local temporary tables are supported with Python 3.6+; older Python
SQLite drivers implicitly commit DDL. Use the existing `mode=ro` file option
when the database itself must reject writes. Keep freshness-sensitive checks
outside the snapshot when they must observe commits made during the read.

The helper serializes its contexts using its public reentrant `lock`. Share
that lock with other uses of the same connection and obey the driver's thread
restrictions. Do not create multiple helpers for one connection, manually
commit/roll back, change isolation mode or reconnect inside a context. An
explicitly replaced driver requires a new helper. PostgreSQL and MySQL
connections are rejected; their transaction behavior is unchanged.
