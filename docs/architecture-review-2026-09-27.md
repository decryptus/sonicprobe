# Architecture review — 2026-09-27

Reviewed commit: `e6c53f6ba591d5f00054c23457f9547282fb7638` on `master`.
Initial status: **review and engineering requirements only**. See the follow-up
implementation below for the addressed findings and compatibility scope.

Scope: separation of application logic, interfaces and adapters; callback and
initialization ownership; fixed validation contracts. Source files were fetched
at the pinned commit. This PR does not change runtime code or claim CI enforcement
of the new requirements. [Pinned source](https://github.com/decryptus/sonicprobe/tree/e6c53f6ba591d5f00054c23457f9547282fb7638).

## Confirmed findings

### S1 — Medium: a legacy utility path re-exports the higher HTTP layer

`sonicprobe/libs/http_json_server.py` consists of a wildcard import from
`httpdis.ext.httpdis_json`. HTTPdis itself imports Sonicprobe helpers, URI utilities
and the threading TCP server. This creates a package-level dependency cycle via
an optional shim, not necessarily a failing Python initialization cycle.

Keep the compatibility shim isolated; new HTTP consumers should import HTTPdis
explicitly, and generic Sonicprobe helpers must not transitively import the shim.
Before removal, identify consumers and make the compatibility decision explicitly.
Acceptance: generic helpers/worker utilities import and run with HTTPdis/DWho
blocked; explicit HTTP adapters remain covered by their transport tests.

### S2 — Medium: PID-file failure handling exits its caller

`libs/daemonize.py:lock_pidfile_or_die` calls `sys.exit(1)` for lock/write failures.
That name advertises termination and is useful at a launcher boundary, but shared
services must not use it as a generic lock/storage operation. Provide or reuse an
exception-returning primitive for embedded use and retain exit mapping in launchers.
The explicit double-fork exits in `daemonize()` are normal daemon lifecycle,
not business/UI coupling and not a request to remove daemonization.

## Positive evidence and limits

No CLI, argparse or curses import was found in the 31 package Python files.
`libs/xbstream.py`'s exit is under the executable main guard, not a generic import
side effect. Other generic modules do not import DWho or HTTPdis in the scanned
source. The existing worker, synchronization and network utilities remain valid
shared adapters; no replacement framework is proposed. This source review does
not rerun every platform, SQL driver or concurrency integration suite.


## Follow-up implementation

S1 is guarded by behavioral import-boundary tests: generic utilities and real
worker execution/shutdown run with HTTPdis/DWho/CLI imports blocked, while an
explicit compatibility test verifies every public shim export by identity against
HTTPdis. The shim and the declared installation dependency remain available;
there is no package-removal or import-path migration in this change.

S2 now has `lock_pidfile()` and `locked_pidfile()`: embedded callers receive a PID
or an exception and control their own lifecycle. `lock_pidfile_or_die()` delegates
to the primitive and preserves launcher exit status 1. The existing daemon context
and double fork retain their contracts. Temporary-file cleanup covers write and
permission failures, and PID-file read handles are closed explicitly.

Tests cover contention, filesystem failures, cleanup, context exceptions,
legacy launcher behavior and separate-process locking. The `/proc`-dependent
contention test runs only when `/proc/self` and `os.getpid()` use the same PID
namespace; the lower-level hard-link contention test remains independent of that
condition. Existing worker, lock, TCP/UDP and pinned-consumer suites remain CI gates.
