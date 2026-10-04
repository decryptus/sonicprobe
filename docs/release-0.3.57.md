# Sonicprobe 0.3.57

This release combines the XYS, network, utility and Keystore reviews in PRs
[#10](https://github.com/decryptus/sonicprobe/pull/10),
[#11](https://github.com/decryptus/sonicprobe/pull/11),
[#12](https://github.com/decryptus/sonicprobe/pull/12) and
[#13](https://github.com/decryptus/sonicprobe/pull/13).

## Corrections

- XYS schema construction no longer changes PyYAML's global safe loader. Validator
  bounds are isolated, malformed/duplicate schema definitions are rejected, and
  existing consumer schemas retain their tested behavior.
- Network validation handles empty/wrong-type inputs consistently, rejects trailing
  junk and corrects IPv6, IDNA, wildcard, port and MAC boundary cases.
- URI/XML parsing, MySQL configuration includes, SQL adapters, OpenVPN, serial/TCP,
  XBStream, certificate helpers and server resource cleanup receive targeted fixes.
- Keystore retains section ownership across deletion/recreation, honors nonblocking
  acquisitions and coordinates global/section ownership to avoid circular waits.

## Compatibility notes

Callers combining Keystore global and section locks must check acquisition results.
A global promotion while the caller owns a section and other threads own sections
returns `None` immediately (`try_lock` retains False/0 failure conventions), with
existing ownership retained. Prefer global ownership before section ownership.
Removing a missing section key raises `KeyError` with either lock flag.

Malformed XML and truncated binary records now fail explicitly. SPSerial reads
return bytes; OpenVPN exposes UTF-8 text over a binary socket. Missing requested
stream terminators raise `EOFError`. XBStream supports P/E records only and does
not validate checksums. MySQL includes are now processed rather than ignored.

Python 2.7.18 and Python 3.5–3.14 remain in the CI matrix. The combined local core
suite collected 198 cases: 197 passed and one `/proc` namespace check was skipped.
The local CertLord consumer checks passed 244 cases; four integration cases passed.
Release CI also checks installed wheels/source distributions and pinned consumers.

These are source reviews and regression checks, not certification of every backend,
thread schedule or external consumer. Real MySQL/PostgreSQL servers, serial
hardware, OpenVPN daemons and backup restores were not accepted by this review.
See the [review inventory](https://github.com/decryptus/sonicprobe/blob/v0.3.57/docs/library-review-status.md)
and its linked reports for precise coverage and remaining limits.

Install with `python -m pip install sonicprobe==0.3.57`.
