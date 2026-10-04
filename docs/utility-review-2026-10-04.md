# Utility library review — 2026-10-04

This pass reads the remaining modules under `sonicprobe/libs` at master
`b83a966f547540b060a8c2785f20533e594122ae`, after the separate
[XYS review](https://github.com/decryptus/sonicprobe/pull/10) and
[network review](https://github.com/decryptus/sonicprobe/pull/11).
It is a source and behavioral review, not certification of every integration,
input combination or thread interleaving. No application deployment is involved.

## Coverage and findings

| Module | Work and evidence | Remaining limits |
| --- | --- | --- |
| `urisup` | Entire source read; regression tests for full input consumption, empty schemes, zero query values, encoding round trips | Legacy empty/absent coalescing and malformed percent escapes retained; not a URL access policy or complete RFC conformance suite |
| `xml2dict` | All methods read; truncated XML now rejected; mixed text, attributes, repetitions and parser reuse tested | Trusted bounded XML only; no new DTD/entity/resource-budget policy |
| `mysql_config_parser` | All methods read; Python 3 `readfp`, byte version output, zero version components, includes, cycles, reload and overrides tested | No live MySQL command; legacy version-output grammar retained; relative include paths remain relative to working directory |
| `openvpn` | All methods read; byte/text conversion, complete writes, line framing, fragmented markers, EOF, timeout restoration and failed connection cleanup tested | Socket doubles, no real management daemon; caller must set timeouts and bound response size; UTF-8 text API |
| `sp_serial` | All methods read; TCP binary I/O, EOF, markers, timeout restoration, close and failed connection cleanup tested | Optional serial/XMODEM dependencies doubled; no hardware transfer; reads return bytes; TCP endpoint syntax remains IPv4/hostname:port |
| `xbstream` | All methods read; binary P/E chunks, little-endian lengths, fragmented reads, short writes, truncation, callback failures tested | No real backup restore; checksums are forwarded, not verified; sparse/unknown chunks explicitly unsupported; entire chunk buffered without a new size cap |
| `anysql` | All entry points read; row slices, DBAPI registration errors, healthy fetch failures and safe reconnect logs tested; existing strict transaction tests rerun | Legacy automatic replay/commit recovery remains enabled by default; use `auto_reconnect=False` for caller-owned transactions; `querymany` limitations retained |
| `BackSQL/backmysql` | All functions read; bound session parameters, compression=0, connection cleanup and conversion-list isolation tested | Driver double; no live server/driver acceptance |
| `BackSQL/backpostgresql` | All functions read; embedded identifier quotes now doubled, with regression test | Driver double; legacy URI query options remain ignored; cast type is trusted SQL |
| `BackSQL/backsqlite3` | All functions read; in-memory URI canonicalization fixed; existing real SQLite transaction, timeout and connectivity tests rerun | No claim for every SQLite build or concurrent workload |
| `daemonize` | All functions read; closes extra `/dev/null` descriptor after redirection; existing PID-file tests rerun | Fork/redirection correction tested with doubles; legacy PID files require a trusted directory; local `/proc` identity test may skip under mismatched namespaces |
| `gencert` | All methods read; explicit zero days honored, invalid key bit counts rejected, exports use context managers; existing real key/CSR/certificate tests rerun | Existing explicit legacy digests retained; exports still require trusted paths; CSR extension policy belongs to issuer; pyOpenSSL migration separate |
| `threading_tcp_server` | All methods read; accepted requests closed if verification raises; real loopback, saturation and shutdown tests rerun | Running handlers are not forcibly interrupted; constructor-failure and all recycling races not exhaustively explored |
| `threading_udp_server` | Same source/control-flow review and tests as TCP | Same lifecycle limitations; legacy HTTP-named aliases retained |
| `workerpool` | All methods read; existing producer/backpressure, callback, recycling, failure and shutdown tests rerun | No formal scheduling/fairness proof; running user callbacks cannot be forcibly stopped |
| `moresynchro` | All methods read; existing ownership, reentrancy, writer timeout and interruption tests rerun | No exhaustive scheduling proof; Python 2 clock fallback remains wall time |
| `keystore` | All methods read; existing global/section lock, creation race and error cleanup tests rerun | Concurrent section deletion/recreation and explicit section-lock lifetimes still need a dedicated lifecycle design/review; do not infer comprehensive race freedom from current tests |
| `http_json_server` | Entire shim read; existing architecture/import tests rerun | Explicit HTTPdis compatibility import only; not a new generic dependency |
| `BackSQL/__init__`, `libs/__init__` | Package initializers read | Backend import registration remains process-global |

Modules outside `libs` (helpers, validators, logging) are **not** declared reviewed
function by function in this pass. Earlier targeted work is recorded in
[REVIEW.md](REVIEW.md) and [CONCURRENCY_REVIEW.md](CONCURRENCY_REVIEW.md).

## Behavior changes to review before merging

- Invalid/truncated XML raises `ExpatError` instead of yielding a partial dictionary.
- URI splitting retains the entire fragment so validation rejects embedded raw
  newlines; it no longer silently drops the suffix. Numeric zero query fields survive.
- MySQL `read()` now actually processes include directives. Includes are traversed
  in sorted directory order, files are closed, cycles and depth over 64 fail explicitly.
  Each versioned load rebuilds configuration; separate custom files override defaults.
- OpenVPN uses UTF-8 strings externally and bytes on the socket. `writeline` sends
  all bytes and returns their count. Line reads accept LF or CRLF. Missing requested
  markers/line terminators raise `EOFError`; `readuntil(None)` still reads to EOF.
  `readlinesuntil` requires a nonempty marker and discards only the matching line.
- SPSerial now consistently returns bytes for binary serial/TCP reads. A missing
  requested marker raises `EOFError` on EOF or an empty timed read, and temporary
  timeouts are restored even when the original timeout was `None` or I/O raises.
  TCP writes use `sendall`; `close()` releases the owned transport.
- XBStream callbacks consume bytes. Short writes advance from the acknowledged
  offset; zero/negative/oversized write progress raises rather than recursing forever.
  I/O errors propagate. Truncated chunks raise `EOFError`. Only P/E records are
  supported; unsupported records are rejected instead of misinterpreted.
- SQL identifier quoting and session parameters are separated from SQL data.
  Reconnect logs intentionally omit the full URI and query because both can contain
  credentials or application data. Healthy fetch failures no longer reconnect.
- `GenCert(notafter_days=0)` no longer silently substitutes 365 days. No new
  certificate validity or issuance policy is implied.

The P/E fixture layout was checked against Percona's upstream
[xbstream reader](https://github.com/percona/percona-xtrabackup/blob/8.0/storage/innobase/xtrabackup/src/xbstream_read.cc):
4-byte path length, 8-byte payload length/offset, then 4-byte checksum. Synthetic
fixtures exercise framing; they do not validate checksums or recovery of a backup.

## Validation

Local Python 3.12: collection guard and full unittest suite, installed-wheel run
outside the source checkout, consumer tests and combined XYS/network candidate
checks are recorded in the pull request. CI covers Python 2.7.18 and 3.5–3.14,
pinned consumer suites, wheel and source-distribution contents. A pending CI run
is not a passed check. No version bump, merge, publication or deployment is part
of this review.
