# Network helper review — 2026-10-04

Scope: `sonicprobe/libs/network.py` at baseline
`b83a966f547540b060a8c2785f20533e594122ae`, its public functions and the direct
call sites found in DWho, CertLord, Covenant, NSAProxy, `urisup` and
`sonicprobe.validator.email`. This is a module review, not certification of all
Sonicprobe libraries or of complete network protocols.

## Confirmed defects and corrections

| Area | Reproduced defect | Correction |
| --- | --- | --- |
| IPv4 predicates | Empty string indexes past its end; wrong types can raise | Return `False`; retain legacy numeric forms |
| IPv4 normalization | libc can ignore whitespace and following junk | Reject whitespace before `inet_aton` |
| CIDR prefix | A Unicode digit such as superscript two passes `isdigit` but raises in `int` | Reject failed numeric conversion |
| IPv6 | Signed, whitespace-padded or overlong hex groups accepted | Require 1–4 ASCII hex digits |
| IPv6 dotted tail | Legacy hexadecimal IPv4 octets accepted inside IPv6 | Require four canonical decimal octets |
| Domain/email/MAC predicates | `$` accepts a final newline | Match through `\Z` |
| Hostnames and certificates | IDNA encoding produces bytes, rejected by text validators on Python 3 | Validate the encoded text representation |
| IDNA helpers | Invalid labels can raise through predicates; encoded bytes cannot round-trip on Python 3 | Handle codec errors and accept bytes for decoding |
| Certificate parsing | Ordinary names reported as wildcard | Set wildcard only when `*.` was present |
| Email | One-character local part rejected | Accept a separator after one character |
| Ports | Floats silently truncated; booleans accepted; `None` raises | Accept integers and integer strings, reject other types |
| MAC normalization | `findall` silently discards surrounding garbage | Check the whole input before normalization |

The IPv6 syntax checks follow the hex-group and embedded IPv4 grammar in
[RFC 3986 section 3.2.2](https://www.rfc-editor.org/rfc/rfc3986#section-3.2.2).
The implementation remains independent of an `ipaddress` backport and preserves
the project's supported legacy interpreters. A generated corpus is compared with
`socket.inet_pton` in the regression suite; this is not exhaustive conformance.

## Compatibility deliberately retained

- `valid_ipv4` and `normalize_ipv4_dotdec` use the system `inet_aton` grammar:
  short addresses and integer/hex forms remain supported. Do not use these as a
  strict canonical-IP policy or an SSRF authorization rule.
- Despite its name, standalone `valid_ipv4_dotdec` permits hexadecimal octets.
  `urisup.host_type` explicitly documents this historical extension. Its
  `int(part, 0)` interpretation of leading zeroes remains interpreter-dependent;
  harmonizing this grammar needs a separate compatibility decision.
- CIDR helpers still accept prefixes 1–32. `/0` remains unsupported. Parsing
  returns the original address/prefix strings and does not normalize a network.
- Domain masks keep their label-count semantics: `DOMAIN` permits one label,
  `DOMAIN_TLD` requires two, `SUB_DOMAIN_TLD` requires three. No DNS query,
  public-suffix lookup or certificate trust check is performed. A trailing dot
  remains unsupported; NSAProxy removes it before calling the helper.
- Existing domain/email length policies are retained. This pass does not claim
  complete DNS or SMTP length/grammar conformance.
- `encode_idn` still returns bytes by default, text with `text_type=True`, using
  Python's built-in IDNA codec. There is no migration to IDNA 2008/UTS #46.
  `decode_idn` retains its UTF-8 fallback. These converters are not validators.
- `parse_domain_cert` returns encoded text when IDN conversion is enabled and
  correctly distinguishes wildcard from ordinary names. CertLord's explicit
  `SUB_DOMAIN_TLD` policy is unchanged, including its treatment of apex domains.
- Port zero remains valid. Textual integer conversion still follows `int`;
  applications needing strict decimal URI syntax must validate it separately.
- MAC normalizers keep compact, colon, hyphen, space, dotted groups and single-digit-octet
  forms. The historical optional separators remain accepted; zero MAC addresses
  can be normalized but remain rejected by `valid_mac_address`.
- `ipv4_to_long` and `long_to_ipv4` remain conversion functions that can raise on
  bad input. Boolean predicates return `False` for ordinary invalid input.

## Verification and remaining scope

`tests/test_network.py` covers IPv4 conversion/normalization, prefix/CIDR helpers,
IPv6 groups/fragments/addresses, IDNA, hostname and certificate masks, email,
ports and MAC addresses. It includes direct `urisup` integration and call-site
conventions used by DWho, CertLord and NSAProxy. All data is synthetic; no DNS,
production service or external networking is contacted by these tests.

Tests are discovered with the unittest collection guard, then run. The existing
CI additionally runs pinned DWho, HTTPdis, Auton, Covenant and monit-docker suites,
legacy/modern Python matrices, installed wheel and source-distribution checks.
CertLord is also tested locally with the candidate library. Exact results belong
in the pull request, including skipped tests and environment limitations.

This work does not audit all of `urisup`, the SSL probe, DNS provider adapters,
all IDNA edge cases, arbitrary object protocols, OS-specific address grammars or
performance under oversized/adversarial input. The status of the wider library
review is recorded in [library-review-status.md](library-review-status.md).
