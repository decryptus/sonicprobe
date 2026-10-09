# sonicprobe 0.3.59

- Add optional SQLite `ro`, `rw` and `rwc` file modes without changing connections that omit `mode`.
- Add MySQL/MariaDB and PostgreSQL read-only/read-write session modes; `rwc` aliases `rw` and does not create server databases.
- Reject invalid or duplicate modes before connecting; explicit modes never silently fall back.
- Expose the underlying driver connection for backend-specific adapters and allow an explicit SQLite thread-check option.
- Validate access modes against real MySQL 8.4, MariaDB 11.4 and PostgreSQL 16 servers, with the existing Python compatibility matrix preserved.

Read-only transaction defaults are separate from database account privileges.
See [SQL access modes](sql-access-modes.md) for the supported behavior and examples.

Install with `python -m pip install sonicprobe==0.3.59`.
