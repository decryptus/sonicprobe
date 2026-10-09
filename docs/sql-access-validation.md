# SQL access-mode validation

The unit suite exercises mode-free compatibility, rejected modes, escaped paths,
SQLite read-only enforcement, absent-file behavior, transaction boundaries,
connection loss and driver setup failures. It also checks explicit worker-thread
access without changing SQLite's default thread check.

`sql_integration` is a separate unittest suite. It requires three explicitly
configured disposable local databases and fails if any target is missing. The
`sql-access-modes` CI job in `tests.yml` supplies MySQL 8.4, MariaDB 11.4 and
PostgreSQL 16 and exercises the installed package outside the checkout.
The acceptance suite checks real DML/DDL refusal, read/write commit and rollback,
read-only persistence across transaction boundaries and reconnection, `rwc`
aliases and failure to open a missing server database. Mock-driver tests alone
are not server acceptance evidence.

Run the collection guard before each suite; the legacy Python matrix remains
required. Explicit SQLite URI-mode tests skip only on runtimes that cannot
implement that API; absence of SQL servers is never a successful skip.
