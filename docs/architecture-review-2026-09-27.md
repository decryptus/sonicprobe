# Architecture review — 2026-09-27

Reviewed commit: `e6c53f6ba591d5f00054c23457f9547282fb7638` on `master`.
Status: **review and engineering requirements only; runtime findings remain open**.

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
