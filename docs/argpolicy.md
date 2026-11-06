# Argument and environment policies

`sonicprobe.libs.argpolicy` validates literal argument lists and environment
mappings independently of applications, HTTP, files, process execution and XYS.
It returns the original object unchanged or raises `ValidationError`. Compile
`ArgsPolicy` / `EnvPolicy` once for repeated calls; invalid configuration raises
`PolicyError`. Exception messages omit supplied values.

```python
from sonicprobe.libs.argpolicy import ArgsPolicy, validate_env

policy = ArgsPolicy({
    'month': {'regex': r'20[0-9]{2}-(0[1-9]|1[0-2])',
              'nargs': '+', 'repeatable': True},
    'verbose': {'nargs': 0},
})
args = ['--month', '2026-09', '2026-10', '--verbose', '--month=2026-11']
assert policy.validate(args) is args
validate_env({'TZ': 'UTC'}, allow={'TZ': {'choices': ['UTC', 'Europe/Paris']}})
```

`validate_args(args, allow=False, disallow=False)` and
`validate_env(env, allow=False, disallow=False)` are convenience functions.
`allow` accepts a boolean, a list of names (optionally single-name mappings), or
a mapping of names to rules. A bare argument name becomes a long option:
`month` matches `--month`, never `-m`, `--mon` or `-month`. Explicit `-m` and
`--month` names are accepted. Duplicate normalized names are configuration
errors. Environment names are literal, case-sensitive identifiers.

A simple name accepts any single value, without repetition. A string rule is
regex shorthand. Detailed rules support `regex`, `choices` and, for arguments,
`nargs` (a nonnegative integer, `+`, or `*`) and `repeatable` (boolean).
A zero-argument option cannot have value constraints. Regexes use full matching
and a 50 ms deadline per value. Both regex and choices apply if configured.
Python 2 uses a disposable matching process because its regex engine has no
native timeout; this adds per-value process overhead. Modern Python uses the
engine deadline directly. Both paths validate without changing the input.
Patterns are limited to 1024 characters and input strings to 65536 characters;
NUL bytes are rejected. The `regex` package is a declared dependency.

`disallow` accepts a boolean or a list of names and always overrides `allow`.
`allow=True` permits positional arguments and repeats unchanged. With a deny
list, exact option names are checked before a literal `--`, and ambiguous
compact short forms are rejected. Program-specific aliases cannot be inferred.
With selective rules, positionals, `--`, unknown options, abbreviations and
short-option clusters are rejected. A value beginning with an option-like dash
must use `--name=VALUE`; negative numbers may also be separate tokens.

Every occurrence and every value is validated. The original token list is
returned without regrouping, splitting attached values, interpolation or other
rewriting. Parsing for validation does not determine how the called program
interprets those tokens. The module never opens files or executes commands.
