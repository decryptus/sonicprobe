# XYS schemas

XYS compiles YAML schemas and validates Python data. It does not load application
configuration, resolve credentials or check permissions. Parse configuration with
a safe YAML loader, validate its shape with XYS, then check application-specific
constraints such as file access and the consistency of related settings.

```python
import yaml
from sonicprobe.libs import xys

schema = xys.load('''
name: !!str
port?: !~~between(1,65535) 1
labels?: [ !!str ]
''')
document = yaml.safe_load('name: example\nport: 9810')
assert xys.validate(document, schema)
```

`load(stream)` compiles exactly one schema. Invalid YAML raises a PyYAML exception;
invalid XYS bounds, duplicate fields and cyclic schemas raise `ValueError` (some
cycles are rejected earlier by PyYAML). Build schemas at initialization, not for
every request. `validate(document, schema)` returns a boolean for ordinary invalid
data and logs failures without interpolating document values or dynamic keys.
Custom validators and modifiers are application code: their exceptions propagate.

## Fields and collections

| Schema form | Meaning |
| --- | --- |
| `name: !!str` | Required string |
| `name!: !!str`, `name+: !!str` | Required string, explicit spelling |
| `name?: !!str` | Optional; if present, must be a string |
| `name*: !!str` | Optional; `null` also accepted |
| `name![1,64]: !!str` | Required string with length 1–64 |
| `name?[0,64]: !!str` | Optional string with length 0–64 |
| `items: [ !!str ]` | List of strings, including an empty list |
| `items: []` | Empty list only |
| `items: !~~seqlen(1,3) [ !!str ]` | One to three strings |
| `value: !!any` | Any Python value |
| `value: !!scalar` | Sonicprobe scalar predicate |

Undeclared dictionary keys are rejected. Scalar examples describe types rather
than literal values: `port: 0` accepts an integer, not only zero. Boolean and
integer schemas are distinct. `!~~fixedStr` and `!~~fixedInt` match literal values.
A comma in a document string remains a comma; XYS does not split it.

For compatibility, a list schema containing multiple mappings merges those
mappings as the schema for **each** item; it is not a tuple schema. Later mapping
entries override earlier ones. Multiple scalar entries retain the historical
first-entry behavior; prefer a single entry for unambiguous new schemas.

Dynamic mapping keys can use validators:

```yaml
env*:
  !~~regex? (0,64) app.envname: !!str
```

Register `app.envname` with `add_regex` first. `(0,64)` limits the number of matching
keys. `+` requires at least one match; `?` permits none unless an explicit positive
minimum is supplied. Each use of a validator has independent bounds. Literal
required fields and mandatory dynamic groups are processed before optional
dynamic groups, then optional literal fields, preserving existing precedence.

## Qualifiers and extensions

Built-ins include `between`, `seqlen`, `enum`, `ienum`, `fixedStr`, `fixedInt`,
`startswith`, `prefixedDec`, `isBool`, `isFloat`, `digit`, `uint`, `callback`,
`isIn` and `regex`. Parameterized tags use commas inside parentheses. Integer
parameters accept signs; enum parameters remain literal strings, including `01`.

`add_validator(function, base_tag, tag=None)` registers a function taking
`(document_value, schema_value)`. `add_parameterized_validator` passes additional
tag parameters. `add_callback`, `add_list`, `add_regex` and `add_modifier` retain
their existing registration APIs. Registries are shared: use namespaced names and
register before starting workers. This change does not make concurrent registry
mutation safe. Existing schemas may retain registered validator functions.

`add_regex` keeps the supplied matcher behavior: a `.match` remains a prefix
match; use a full matcher when the application requires it. No regex execution
time limit is added here.

## Modifiers and legacy conversions

`name|strip,lower: !!str` applies string methods in order. A name registered with
`add_modifier` takes precedence over a method. Each modifier runs **once** per
field and updates the original dictionary in place. Unknown modifier names retain
the historical no-op behavior. Validation is not transactional: earlier changes
remain if a later field fails. Copy a document before validation when necessary.

For compatibility, optional fields with minimum length zero may accept an empty
string before type checking, including after a modifier. `*` accepts a null result
from a modifier. Avoid these forms when strict type checking is required.

Legacy conversion qualifiers are intentionally not tightened in this cleanup:
`uint` means strictly positive, `isFloat` accepts float-convertible values including
nonfinite values, and `isBool` accepts numeric equivalents of booleans. Use strict
YAML scalar schemas and explicit application checks for stricter requirements.

## Loading and compatibility changes

XYS now owns a `SafeLoader` subclass. Standard YAML data tags, ordinary aliases,
merge keys and XYS extensions are supported; Python-object tags are rejected.
XYS tags are no longer injected into global `yaml.Loader`/`yaml.FullLoader`
registries. Call `xys.load`, rather than relying on that import side effect.
Custom schema constructors, if needed, must target `xys.SchemaLoader` explicitly.

Intentional corrections compared with Sonicprobe 0.3.56:

- Per-node occurrence bounds cannot leak into subsequent schemas.
- Modifiers execute once rather than twice.
- `[]` rejects a nonempty list instead of raising `IndexError`.
- Literal non-string keys can describe nested collections.
- Signed numeric ranges and numeric-looking enum strings work.
- Non-decimal Unicode digit strings do not crash `uint`.
- Explicit duplicate keys and collisions after qualifier removal are rejected.
- Reversed field/occurrence bounds and empty or unbalanced tag parameters are
  rejected during schema loading.
- Recursive schemas are rejected; ordinary shared aliases remain valid.

These changes are not a guarantee that arbitrary untrusted schemas are safe to
accept. Schemas and extension code remain trusted application inputs. Bound input
size/depth in the caller; deeply nested documents, expensive callbacks and regexes
are not given CPU or memory budgets by XYS.

## Verification scope

`tests/test_xys.py` covers compilation, registration isolation, occurrence bounds,
modifiers, types and collection behavior. `tests/test_xys_safe_logs.py` checks log
redaction. `tests/test_xys_consumers.py` exercises 20 frozen public schemas from
Auton, Covenant, CertLord and NSAProxy, with source paths and Git blob hashes in
`tests/xys_consumer_fixtures.py`. These fixtures check schema contracts, not complete
applications; application integration tests remain necessary.

A local comparison against commit `b83a966f547540b060a8c2785f20533e594122ae`
found identical results and document mutations for 760 representative and mutated
consumer inputs. The intended bug fixes above have separate regression tests.
The existing CI also exercises pinned DWho, HTTPdis, Auton, Covenant and
monit-docker consumers and the supported Python interpreter matrix.
