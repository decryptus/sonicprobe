# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate literal argv/environment inputs without rewriting or executing them.

Policies are compiled once. Regex evaluation uses the ``regex`` engine
with a deadline; absence of that engine is a configuration error, never a bypass.
"""
import re
import six

OPTION_NAME = re.compile(r'^(?:--?)?[A-Za-z][A-Za-z0-9_-]*\Z')
ENV_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*\Z')
NEGATIVE_NUMBER = re.compile(r'^-\d+(?:\.\d+)?\Z')
RULE_FIELDS = frozenset(('regex', 'choices', 'nargs', 'repeatable'))
MAX_RULES = 256
MAX_PATTERN = 1024
MAX_VALUE = 65536
REGEX_TIMEOUT = 0.05


class PolicyError(ValueError):
    """Invalid policy configuration (never includes supplied values)."""


class ValidationError(ValueError):
    """Input rejected by a valid policy (never includes supplied values)."""


def option_name(name):
    if not isinstance(name, six.string_types) or not OPTION_NAME.match(name):
        raise PolicyError('invalid option name')
    return name if name.startswith('-') else '--' + name


def env_name(name):
    if not isinstance(name, six.string_types) or not ENV_NAME.match(name):
        raise PolicyError('invalid environment variable name')
    return name


def _entries(spec, normalize, rules):
    if type(spec) is bool:
        return spec
    if isinstance(spec, dict) and rules:
        entries = list(spec.items())
    elif isinstance(spec, list):
        entries = []
        for item in spec:
            if isinstance(item, six.string_types):
                entries.append((item, None))
            elif rules and isinstance(item, dict) and len(item) == 1:
                entries.extend(item.items())
            else:
                raise PolicyError('expected names or single-name rule mappings')
    else:
        raise PolicyError('expected a boolean, name list or rule mapping')
    if len(entries) > MAX_RULES:
        raise PolicyError('too many policy rules')
    result = {}
    for name, rule in entries:
        name = normalize(name)
        if name in result:
            raise PolicyError('duplicate policy name: ' + name)
        result[name] = rule
    return result


class _Rule(object):
    def __init__(self, name, spec, arguments):
        self.name = name
        if spec is None or spec is True:
            spec = {}
        elif isinstance(spec, six.string_types):
            spec = {'regex': spec}
        if not isinstance(spec, dict) or set(spec) - RULE_FIELDS:
            raise PolicyError('invalid rule for ' + name)
        if not arguments and set(spec) & {'nargs', 'repeatable'}:
            raise PolicyError('environment rules do not accept nargs or repeatable')
        self.nargs = spec.get('nargs', 1)
        if not ((type(self.nargs) is int and 0 <= self.nargs <= MAX_RULES)
                or (isinstance(self.nargs, six.string_types) and self.nargs in ('+', '*'))):
            raise PolicyError('nargs must be a nonnegative integer, + or *')
        self.repeatable = spec.get('repeatable', False)
        if type(self.repeatable) is not bool:
            raise PolicyError('repeatable must be boolean')
        self.choices = spec.get('choices')
        if 'choices' in spec and (not isinstance(self.choices, list)
                or not self.choices or len(self.choices) > MAX_RULES
                or any(not isinstance(v, six.string_types) or '\x00' in v
                       or len(v) > MAX_VALUE for v in self.choices)):
            raise PolicyError('choices must contain strings')
        if self.choices is not None:
            self.choices = tuple(self.choices)
        self.pattern = None
        if 'regex' in spec:
            pattern = spec['regex']
            if not isinstance(pattern, six.string_types) or len(pattern) > MAX_PATTERN:
                raise PolicyError('invalid regex for ' + name)
            try:
                import regex
            except ImportError:
                raise PolicyError('regex rules require the regex package')
            try:
                self.pattern = regex.compile(pattern)
            except regex.error:
                raise PolicyError('invalid regex for ' + name)
        if self.nargs == 0 and (self.pattern is not None or self.choices is not None):
            raise PolicyError('valueless options cannot have value rules')

    def validate(self, value):
        if self.choices is not None and value not in self.choices:
            raise ValidationError('value outside choices for ' + self.name)
        if self.pattern is not None:
            try:
                valid = self.pattern.fullmatch(value, timeout=REGEX_TIMEOUT)
            except Exception as error:
                if type(error).__name__ != 'TimeoutError':
                    raise
                raise ValidationError('regex deadline exceeded for ' + self.name)
            if valid is None:
                raise ValidationError('value does not match regex for ' + self.name)


def _text(value):
    if not isinstance(value, six.string_types) or '\x00' in value or len(value) > MAX_VALUE:
        raise ValidationError('expected bounded text without NUL bytes')


def _option(token):
    return token.startswith('-') and token != '-' and not NEGATIVE_NUMBER.match(token)


class ArgsPolicy(object):
    """Compile allow/deny policies. Bare ``month`` means exactly ``--month``.

    A simple name consumes one value and cannot repeat. Rules accept ``nargs``
    (0, a fixed count, + or *), ``repeatable``, ``regex`` and ``choices``.
    Restricted policies reject positionals, short clusters and abbreviations.
    """
    def __init__(self, allow=False, disallow=False):
        self.allow = _entries(allow, option_name, True)
        self.disallow = _entries(disallow, option_name, False)
        if isinstance(self.allow, dict):
            self.allow = {name: _Rule(name, rule, True) for name, rule in self.allow.items()}

    def _denied(self, name):
        return self.disallow is True or (isinstance(self.disallow, dict) and name in self.disallow)

    def validate(self, args):
        if not isinstance(args, list):
            raise ValidationError('arguments must be a list')
        for value in args:
            _text(value)
        if args and (self.allow is False or self.disallow is True):
            raise ValidationError('client arguments are forbidden')
        if self.allow is True:
            # Without an option grammar only exact options can be denied. Reject
            # ambiguous compact short forms when exceptions are configured.
            for token in args:
                if token == '--':
                    break
                if _option(token):
                    name = token.split('=', 1)[0]
                    if self._denied(name):
                        raise ValidationError('forbidden option: ' + name)
                    if self.disallow and name.startswith('-') and not name.startswith('--') and len(name) > 2:
                        raise ValidationError('compact short options are ambiguous with a deny list')
            return args
        seen, index = set(), 0
        while index < len(args):
            token = args[index]
            name, separator, attached = token.partition('=')
            if name not in self.allow or self._denied(name):
                raise ValidationError('unknown or forbidden option at argument %d' % index)
            rule = self.allow[name]
            if name in seen and not rule.repeatable:
                raise ValidationError('option cannot repeat: ' + name)
            seen.add(name)
            values = [attached] if separator else []
            index += 1
            maximum = rule.nargs if type(rule.nargs) is int else None
            minimum = maximum if maximum is not None else (1 if rule.nargs == '+' else 0)
            while (maximum is None or len(values) < maximum) and index < len(args) and not _option(args[index]):
                values.append(args[index])
                index += 1
            if len(values) < minimum or (maximum is not None and len(values) != maximum):
                raise ValidationError('wrong value count for ' + name)
            for value in values:
                rule.validate(value)
        return args


class EnvPolicy(object):
    """Validate environment names and values, returning the original mapping."""
    def __init__(self, allow=False, disallow=False):
        self.allow = _entries(allow, env_name, True)
        self.disallow = _entries(disallow, env_name, False)
        if isinstance(self.allow, dict):
            self.allow = {name: _Rule(name, rule, False) for name, rule in self.allow.items()}

    def validate(self, env):
        if not isinstance(env, dict):
            raise ValidationError('environment must be a mapping')
        for name, value in env.items():
            try:
                env_name(name)
            except PolicyError:
                raise ValidationError('invalid environment variable name')
            _text(value)
            if (self.allow is False or self.disallow is True
                    or isinstance(self.disallow, dict) and name in self.disallow
                    or isinstance(self.allow, dict) and name not in self.allow):
                raise ValidationError('forbidden environment variable: ' + name)
            if isinstance(self.allow, dict):
                self.allow[name].validate(value)
        return env


def validate_args(args, allow=False, disallow=False):
    """Compile and validate once; use ArgsPolicy for repeated validation."""
    return ArgsPolicy(allow, disallow).validate(args)


def validate_env(env, allow=False, disallow=False):
    """Compile and validate once; use EnvPolicy for repeated validation."""
    return EnvPolicy(allow, disallow).validate(env)
