# SQLite transaction helper validation

The optional helper is separate from connection establishment and schema
ownership. It reuses a strict AnySQL connection, shares one reentrant lock and
does not change existing adapter defaults or introduce application imports.

Eleven focused cases exercise actual SQLite WAL snapshots and writer contention,
committed visibility, nested contexts, rollback after a `BaseException`, failed
BEGIN ownership, deferred-constraint commit failures, explicit reconnection,
uncertain cleanup and incompatible connection rejection. Temporary-table DDL is
tested on Python 3.6+; older sqlite3 drivers implicitly commit DDL and that
specific case is explicitly skipped there.

Local Python 3.12 collection found 240 unit declarations and 240 cases. Execution
passed with one existing process-namespace skip in the daemonization suite.
The new helper cases all passed. Supported interpreter, installed distribution,
consumer and optional SQL server checks remain part of the release CI gates.

WAL behavior depends on the application's journal configuration and filesystem.
These tests do not establish throughput limits or qualify any external workload.
