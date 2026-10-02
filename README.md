# sonicprobe

A collection of Python infrastructure utilities used by
[dwho](https://github.com/decryptus/dwho),
[HTTPdis](https://github.com/decryptus/httpdis), Covenant and Auton.
The name belongs to this ecosystem's **Doctor Who** theme. Independent software;
not affiliated with the television series.

## What is here?

| Area | Modules |
| --- | --- |
| Background execution | `workerpool`, TCP/UDP threaded servers |
| Configuration and data | YAML helpers, `xys`, URI and network validation |
| Databases | `anysql`, SQLite/MySQL/PostgreSQL adapters |
| System utilities | files, base64, daemonization, keystore and locks |
| Specialized integrations | certificates, OpenVPN, serial, xbstream, email logging |

The value is shared behavior for existing services. This is a broad toolkit,
not a standalone monitoring product. Import only the functionality you need.

## Install

```sh
python -m pip install sonicprobe
```

Python 2.7 and Python 3.5+ remain declared for compatibility. Use maintained
Python for new deployments; older interpreters need older dependency versions.
Native integrations may require libcurl, libmagic and system development headers.
MySQL, PostgreSQL and serial integrations need their respective optional drivers
(`mysqlclient`, `psycopg2`, `pyserial`, `xmodem`). CI covers core regressions; it does
not run real database servers, serial hardware, OpenVPN or certificate authorities.

## Worker pool

```python
import threading
from sonicprobe.libs.workerpool import WorkerPool

finished = threading.Event()
result = []
pool = WorkerPool(max_workers=2, name='example')
pool.run_args(lambda value: value * 2, 21,
              _callback_=result.append,
              _complete_=lambda value: finished.set())
if not finished.wait(10):
    raise RuntimeError('Task did not finish')
pool.killall(2)
assert result == [42]
```

`run` reserves `callback`, `name`, `complete` and `qpriority`; `run_args` reserves
`_callback_`, `_name_`, `_complete_` and `_qpriority_`. Other arguments reach the
callable. Completion runs even when the task fails. Callback errors are logged.
Workers wait on the queue rather than spinning. `max_tasks` and `life_time`
control recycling. With a `PriorityQueue`, lower priorities run first and equal
priorities preserve submission order. Submit priority tasks through the pool API.

`killall(wait)` rejects further submissions, cancels queued work and waits up to
`wait` seconds for active workers (`None` waits indefinitely). It does not forcibly
interrupt running Python functions. `killable()` reports a momentary idle state,
not a synchronization barrier. `tasks.join()` waits for submitted queue work.

The concurrency changes in 0.3.53 and their consumer tests are described in the
[September 23 concurrency review](docs/CONCURRENCY_REVIEW.md). These primitives
coordinate threads within one process; create fresh workers and locks after
process creation. When combining explicit Keystore locks, acquire the global
lock before section locks and release them in reverse order. Do not fork a
process while its application threads are using these objects.

## Files and SQL

```python
from sonicprobe import helpers
encoded = helpers.base64_encode_file('/tmp/input.bin')
# Output can instead be streamed to a destination filename with dst=...
```

File helpers close their input streams, including streams passed by the caller.
Base64 decoding accepts wrapped input. Invalid tiny chunk sizes raise `ValueError`
instead of silently returning truncated results. In-memory file accumulation uses
chunk lists to avoid repeated copying of a growing byte string.

```python
from sonicprobe.libs import anysql
connection = anysql.connect_by_uri('sqlite3::memory:?timeout_ms=250')
try:
    cursor = connection.cursor()
    cursor.query('SELECT 1')
    print(cursor.fetchone())
finally:
    connection.close()
```

SQLite's `timeout_ms` is interpreted in milliseconds. Values should be bound via
query parameters; do not concatenate untrusted SQL fragments.

For application-managed transactions, use
`anysql.connect_by_uri(uri, auto_reconnect=False)`. Query, fetch and commit
failures then propagate without probing the connection, reconnecting or replaying
work. The caller owns commit, rollback and recovery; this option does not change
DBAPI autocommit. An explicit `reconnect()` remains available. The historical
automatic recovery behavior remains the default for existing callers.

The adapters share a connection interface, not a portable SQL dialect. SQLite
connections retain their driver thread affinity, and SQLite `querymany` is not
currently supported; use parameterized `query` calls inside a transaction.

## Certificates

`GenCert` now defaults to SHA-256, exports PEM bytes correctly and issues X.509 v3
certificates. The legacy OpenSSL object API is preserved by requiring
`pyOpenSSL<26.2` (26.2 removed its extension API). Applications should explicitly
review CSR extensions when issuing certificates. A future API migration to
`cryptography.x509` is needed to remove this compatibility cap.

## Compatibility boundaries

The historical `sonicprobe.libs.http_json_server` re-exports HTTPdis. Consequently
sonicprobe and HTTPdis still depend on each other. This release retains that
installation behavior; a future major version can separate the HTTP compatibility
module and reduce mandatory dependencies. The broad public surface is a maintenance
cost: tested core behavior should not be confused with universal backend coverage.

## XYS validation logs

The development branch keeps XYS validation results unchanged while removing
rejected document values and unexpected document key names from built-in error
logs. Qualifier failures identify the schema validator; length failures identify
the bound, and unknown fields produce a generic forbidden-key message.
Schema-defined expected field names, validator names, types and bounds can still
appear as diagnostics. Callers should inspect the boolean validation result,
rather than depending on exact log text or recovering input values from logs.

This uses no global logging suppression or per-request logger reconfiguration.
It only governs XYS's own diagnostics: application callbacks and custom validators
remain responsible for what they log. Regression tests capture formatted records,
reject synthetic input markers and check that valid documents still pass.

## Tests and release

```sh
python -m pip install -e . mock
python -m unittest discover -s tests -v
python -m pip install build twine
python -m build
python -m twine check --strict dist/*
```

CI tests core workers, helpers, SQL and local server behavior on the configured
interpreter matrix. PyPI publishing is gated by these tests and artifact validation.
Update `VERSION`, `RELEASE` and `setup.yml` together. Merging to master creates a
new `vX.Y.Z` tag and publishes via Trusted Publishing (`decryptus/sonicprobe`,
workflow `pypi.yml`, environment `pypi`). Existing tags are never overwritten.

License: GPL-3.0-or-later; original module copyrights remain in the source.

See the [September 2026 code and architecture review](docs/REVIEW.md) (French).


### Embedded PID-file locking and launcher compatibility

`sonicprobe.libs.daemonize.lock_pidfile(path)` claims a PID file and returns the
current PID. It raises `PidfileLockError` when the lock cannot be claimed and
propagates filesystem exceptions. It does not call `sys.exit()` or fork. Temporary
PID files are cleaned after write or permission failures. Existing Linux `/proc`
stale-file detection, file permissions and atomic hard-link acquisition remain.
As before, this is a process lock, not a lock for threads within one process.
It requires `/proc` to expose the same PID namespace as the caller.

For embedded applications, use the context manager to release your own PID file
on normal completion or an exception:

```python
from sonicprobe.libs.daemonize import locked_pidfile, PidfileLockError

try:
    with locked_pidfile('/run/example.pid') as pid:
        run_application()
except PidfileLockError:
    handle_already_running()
```

Existing launchers keep their contracts: `lock_pidfile_or_die(path)` returns the
PID on success and exits with status 1 on failure; `pidfile_context(path,
foreground=False)` keeps its daemonization, exit and cleanup behavior. The explicit
double fork in `daemonize()` is unchanged. Embedded applications must choose the
new primitive/context explicitly rather than the launcher helpers.

`sonicprobe.libs.http_json_server` remains a compatibility re-export with the same
HTTPdis objects. New HTTP consumers should import `httpdis.ext.httpdis_json`
directly. Generic utilities do not import the shim; tests exercise helpers,
schemas, locks, worker execution/shutdown and PID lifecycle with HTTPdis, DWho and
CLI imports blocked. The declared HTTPdis installation dependency is retained in
this release to avoid breaking consumers that rely on the historical shim.
