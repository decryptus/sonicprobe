# Library review scope — 2026-10-04

A passing test suite and an architecture review are not a complete audit of every
utility. This inventory makes that distinction explicit. It does not erase work
from earlier targeted reviews; see [the September review](REVIEW.md),
[the concurrency review](CONCURRENCY_REVIEW.md), and
[the architecture review](architecture-review-2026-09-27.md).

A module review should identify public entry points and consumers, inspect their
input/output contracts, reproduce discovered failures, add meaningful regression
tests, and report compatibility differences and remaining limits. Tests should
cover valid, invalid, empty, boundary and wrong-type inputs where relevant.
Concurrency/resource-owning modules also need lifecycle and cleanup checks.
Even a completed module review is not a proof that it contains no further bugs.

| Module under `sonicprobe/libs` | Status in this pass |
| --- | --- |
| `BackSQL/backmysql.py` | No complete function-by-function review in this pass |
| `BackSQL/backpostgresql.py` | No complete function-by-function review in this pass |
| `BackSQL/backsqlite3.py` | No complete function-by-function review in this pass |
| `anysql.py` | No complete function-by-function review in this pass |
| `daemonize.py` | No complete function-by-function review in this pass |
| `gencert.py` | No complete function-by-function review in this pass |
| `http_json_server.py` | No complete function-by-function review in this pass |
| `keystore.py` | No complete function-by-function review in this pass |
| `moresynchro.py` | No complete function-by-function review in this pass |
| `mysql_config_parser.py` | No complete function-by-function review in this pass |
| `network.py` | Reviewed in this pass; corrections and tests in a separate PR |
| `openvpn.py` | No complete function-by-function review in this pass |
| `sp_serial.py` | No complete function-by-function review in this pass |
| `threading_tcp_server.py` | No complete function-by-function review in this pass |
| `threading_udp_server.py` | No complete function-by-function review in this pass |
| `urisup.py` | No complete function-by-function review in this pass |
| `workerpool.py` | No complete function-by-function review in this pass |
| `xbstream.py` | No complete function-by-function review in this pass |
| `xml2dict.py` | No complete function-by-function review in this pass |
| `xys.py` | Reviewed in PR #10; awaiting merge approval |

XYS evidence: [PR #10](https://github.com/decryptus/sonicprobe/pull/10).
Network evidence and deliberately retained limitations:
[network-review.md](network-review.md).

Modules outside `sonicprobe/libs` (helpers, validators, logging and adapters) are
not declared fully audited by this inventory. Future reviews must update the
specific module status and attach evidence rather than marking the entire
package as verified.
