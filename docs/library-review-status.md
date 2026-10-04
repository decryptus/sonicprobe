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
| `BackSQL/backmysql.py` | Source and behavior reviewed; see utility review and its limits |
| `BackSQL/backpostgresql.py` | Source and behavior reviewed; see utility review and its limits |
| `BackSQL/backsqlite3.py` | Source and behavior reviewed; see utility review and its limits |
| `anysql.py` | Source and behavior reviewed; see utility review and its limits |
| `daemonize.py` | Source and behavior reviewed; see utility review and its limits |
| `gencert.py` | Source and behavior reviewed; see utility review and its limits |
| `http_json_server.py` | Source and behavior reviewed; see utility review and its limits |
| `keystore.py` | Dedicated lifecycle corrections in PR #13; see Keystore review |
| `moresynchro.py` | Source and behavior reviewed; see utility review and its limits |
| `mysql_config_parser.py` | Source and behavior reviewed; see utility review and its limits |
| `network.py` | Reviewed and corrected in PR #11; see network review |
| `openvpn.py` | Source and behavior reviewed; see utility review and its limits |
| `sp_serial.py` | Source and behavior reviewed; see utility review and its limits |
| `threading_tcp_server.py` | Source and behavior reviewed; see utility review and its limits |
| `threading_udp_server.py` | Source and behavior reviewed; see utility review and its limits |
| `urisup.py` | Source and behavior reviewed; see utility review and its limits |
| `workerpool.py` | Source and behavior reviewed; see utility review and its limits |
| `xbstream.py` | Source and behavior reviewed; see utility review and its limits |
| `xml2dict.py` | Source and behavior reviewed; see utility review and its limits |
| `xys.py` | Reviewed and corrected in PR #10; see XYS guide |

All four review PRs (#10–#13) are merged for 0.3.57. Detailed evidence and limits:
[utility review](utility-review-2026-10-04.md),
[Keystore lifecycle review](keystore-lifecycle-review.md), and [XYS guide](xys.md).

XYS evidence: [PR #10](https://github.com/decryptus/sonicprobe/pull/10).
Network evidence and deliberately retained limitations:
[network-review.md](network-review.md).

Modules outside `sonicprobe/libs` (helpers, validators, logging and adapters) are
not declared fully audited by this inventory. Future reviews must update the
specific module status and attach evidence rather than marking the entire
package as verified.
