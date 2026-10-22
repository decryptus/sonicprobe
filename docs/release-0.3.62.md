# Sonicprobe 0.3.62

The new optional `SQLiteTransactions` helper provides explicit write
transactions and deferred read snapshots for strict AnySQL SQLite connections.
WAL readers can retain a consistent view without reserving the database writer.
Existing AnySQL connection defaults and other database adapters are unchanged.

See [SQLite transactions and read snapshots](sqlite-transactions.md) for usage,
nesting rules, failure behavior and supported driver constraints.

Install with `python -m pip install --upgrade 'sonicprobe==0.3.62'`.
