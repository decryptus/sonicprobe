# Sonicprobe 0.3.64

Adds `sonicprobe.libs.argpolicy`: reusable `ArgsPolicy` / `EnvPolicy` validators
and the `validate_args` / `validate_env` convenience functions. They accept
allow/deny rules, exact names, full-value regexes, choices, repeated options and
fixed or variable value counts. Denials take precedence. Validation returns the
original inputs without rewriting or executing the caller's command.

Regex work is bounded. Modern Python uses the engine deadline; Python 2 uses a
disposable matching process because its engine has no timeout API. The regex
dependency retains a compatible Python 2 version. Invalid configuration is an
explicit error; validation errors omit supplied values.

See the [API guide](argpolicy.md) for syntax and limits. This addition does not
change existing Sonicprobe utility behavior. Auton uses it for its explicit
client input policies.

Install with `python -m pip install --upgrade 'sonicprobe==0.3.64'`.
