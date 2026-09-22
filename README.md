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
