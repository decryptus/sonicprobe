# Engineering requirements

These are maintainer requirements. Existing violations are debt, not examples.
See [the architecture review](docs/architecture-review-2026-09-27.md).

- Business/application behavior must be callable independently of CLI, ncurses,
  web presentation and HTTP request objects. Interfaces translate input, call
  shared services and present results; they are not application engines.
- Never implement an API operation by importing/calling a CLI entry point,
  constructing artificial command arguments or delegating to UI-owned callbacks.
- Put HTTP decoding, headers, status mapping and serialization in transport
  adapters; terminal interaction and exit codes belong to command interfaces.
  Pass explicit data and caller identity to services, with domain results/errors.
- Keep authorization and operation validation server-side. Interface filtering
  and disabled controls do not grant permission or replace service validation.
- Use explicit adapters/composition for storage, execution, clocks and lifecycle.
  Avoid new process-global mutable application state and hidden import side effects.
- Declare fixed routes, field sets, schemas, registries, limits and regex patterns
  as named uppercase module constants. Dynamic per-request objects remain local.
- Centralize identifier validation and use full matching. Preserve this project's
  naming and selector contracts; do not copy Galliflow's grammar here.
- Bound externally supplied regex work where supported, preserve matching semantics,
  and reject invalid selectors explicitly without broadening their selection.
- Reuse DWho, HTTPdis and Sonicprobe according to their roles. A transport library
  may expose HTTP objects; neutral services must not require those objects.
- Inspect lazy imports, callbacks and initialization paths during reviews. For a
  refactor, add behavioral tests with interface imports blocked and fake adapters;
  green functional tests alone do not demonstrate architectural separation.
- Avoid unnecessary production log/disk writes, retaining promised durability.
  Do not claim documentation alone is an automated architecture gate.

## Sonicprobe boundaries

- Generic utilities must not require application libraries or interface entry
  points. Keep optional adapters/shims separate from reusable utility modules.
- libs/http_json_server.py is a legacy HTTPdis re-export, not a generic dependency
  to use from new code. HTTP consumers should use HTTPdis explicitly.
- Daemonization and process exit belong at a launcher boundary. Reusable helpers
  should return results or raise exceptions instead of unexpectedly terminating
  their caller. Explicit daemon fork/exit behavior remains a lifecycle operation.
- Preserve thread/worker shutdown, resource cleanup and existing utility contracts
  when extracting boundaries; do not replace real concurrency tests with imports.
