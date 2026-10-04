# -*- coding: utf-8 -*-
# Copyright 2008-2019 The Wazo Authors
# Copyright (C) 2008-2010 Avencall
# SPDX-License-Identifier: GPL-3.0-or-later
"""XIVO YAML Schema: compile trusted schemas and validate Python data.

See docs/xys.md for syntax, mutation semantics and extension contracts.
"""

from collections import namedtuple

import copy
import re
import logging
import yaml

from six import ensure_text, integer_types, iteritems, string_types, text_type

from sonicprobe import helpers


LOG = logging.getLogger("sonicprobe.xys") # pylint: disable-msg=C0103

# NOTE: content must stay first
ValidatorNode = namedtuple('ValidatorNode', 'content validator mode min max')
_VALIDATOR_MODES = {'+': {'name': 'mandatory', 'min': 1, 'max': None},
                    '?': {'name': 'optional', 'min': 0, 'max': None},
                    '':  {'name': 'optional', 'min': 0, 'max': None}}

Optional = namedtuple('Optional', 'content min_len max_len modifier')
OptionalNull = namedtuple('OptionalNull', 'content min_len max_len modifier')
Mandatory = namedtuple('Mandatory', 'content min_len max_len modifier')

RE_INTEGER_PARAM = re.compile(r'^[+-]?[0-9]+\Z').match

RE_MATCH_TYPE           = type(re.compile('').match)
RE_MATCH_CSTR           = re.compile(r'^(.+?)' +
                                     r'(?:([\?\!\+\*])(?:\[(?:([0-9]+)|([0-9]*),([0-9]*))\]|([\*\+\?]))?)?' +
                                     r'(?:\|((?:(?:[a-zA-Z0-9_][a-zA-Z0-9\-_\.]*)?[a-zA-Z0-9_])' +
                                     r'(?:,(?:[a-zA-Z0-9_][a-zA-Z0-9\-_\.]*)?[a-zA-Z0-9_])*))?' +
                                     r'(\-)?$').match
RE_MATCH_VALIDATOR_CSTR = re.compile(r'^(?:\((?:([0-9]+)|([0-9]*),([0-9]*))\)\s+)?\s*(.+)$').match

_callbacks      = {}
_lists          = {}
_modifiers      = {}
_regexs         = {}


class SchemaLoader(yaml.SafeLoader):
    """Keep schema tags separate from PyYAML's process-wide constructors."""

    def construct_mapping(self, node, deep=False):
        # Check explicit keys before expanding merges; YAML merge overrides
        # remain supported, but repeated explicit keys are ambiguous.
        seen = set()
        for key_node, _ in node.value:
            if key_node.tag == 'tag:yaml.org,2002:merge':
                continue
            key = self.construct_object(key_node, deep=deep)
            try:
                if key in seen:
                    raise ValueError('Duplicate XYS schema key')
                seen.add(key)
            except TypeError:
                raise ValueError('Unhashable XYS schema key')
        return super(SchemaLoader, self).construct_mapping(node, deep=deep)


class Any(object): # pylint: disable=too-few-public-methods,useless-object-inheritance
    pass

class Scalar(object): # pylint: disable=too-few-public-methods,useless-object-inheritance
    pass

def construct_yaml_any(loader, node): # pylint: disable=unused-argument
    return Any()

def construct_yaml_scalar(loader, node): # pylint: disable=unused-argument
    return Scalar()

SchemaLoader.add_constructor('tag:yaml.org,2002:any', construct_yaml_any)
SchemaLoader.add_constructor('tag:yaml.org,2002:scalar', construct_yaml_scalar)


class ConstructorValidatorNode(object): # pylint: disable=useless-object-inheritance
    def __init__(self, tag, base_tag, validator, mode = 'generic', xmin = None, xmax = None):
        self.tag       = tag
        self.base_tag  = base_tag
        self.validator = validator
        self.mode      = mode
        self.min       = xmin
        self.max       = xmax

    def _parser(self, value):
        m = RE_MATCH_VALIDATOR_CSTR(value)
        if not m:
            return value

        if m.group(1) is not None:
            self.min = self.max = int(m.group(1))
        elif m.group(2) is not None:
            if m.group(2):
                self.min = int(m.group(2))
            else:
                self.min = 0
            if m.group(3):
                self.max = int(m.group(3))

        if self.mode == 'mandatory':
            if self.min < 1:
                self.min = 1
        elif self.mode == 'optional':
            if self.min > 0:
                self.mode = 'mandatory'

        return m.group(4)

    def __call__(self, loader, node):
        # PyYAML reuses this constructor across nodes, schemas and threads.
        # Parse occurrence bounds on a private copy, never on the registration.
        current = copy.copy(self)
        node = copy.copy(node)
        if isinstance(node.value, string_types):
            node.value = current._parser(node.value)
        if current.min is not None and current.max is not None and current.min > current.max:
            raise ValueError('Invalid XYS validator bounds')
        return ValidatorNode(
            _construct_node(loader, node, current.base_tag),
            current.validator, current.mode, current.min, current.max)


# Preserve imports of the historical misspelling.
ContructorValidatorNode = ConstructorValidatorNode


def _construct_node(loader, node, base_tag):
    "Warning: depends on python-yaml internals"
    node = copy.copy(node) # bypass YAML anti recursion
    best_tag = base_tag
    best_fit = 0
    for key, val in iteritems(loader.DEFAULT_TAGS):
        lenk = len(key)
        if lenk <= best_fit:
            continue
        if base_tag.startswith(key):
            best_tag = val + base_tag[lenk:]
            best_fit = lenk
    node.tag = best_tag
    return loader.construct_object(node, deep=True)


def _maybe_int(s):
    "Coerce complete decimal integers; keep other symbols unchanged."
    if RE_INTEGER_PARAM(s):
        return int(s)
    return s


def _split_params(tag_prefix, tag_suffix, numeric=True):
    "Split comma-separated tag_suffix[:-1] and map with _maybe_int"
    if tag_suffix[-1:] != ')':
        raise ValueError("unbalanced parenthesis in type %s%s" % (tag_prefix, tag_suffix))
    params = tag_suffix[:-1].split(',')
    if not all(params):
        raise ValueError('Empty XYS validator parameter')
    return list(map(_maybe_int, params)) if numeric else params


def add_callback(name, value):
    if not hasattr(value, '__call__'):
        raise TypeError("%r is not callable" % value)
    if name in _callbacks:
        raise ValueError("%s is already registered" % name)

    _callbacks[name] = value


def add_list(name, value):
    try:
        iter(value)
    except TypeError:
        raise TypeError("%r is not iterable" % value)

    if name in _lists:
        raise ValueError("%s is already registered" % name)

    _lists[name] = value


def add_modifier(name, value):
    if not hasattr(value, '__call__'):
        raise TypeError("%r is not callable" % value)
    if name in _modifiers:
        raise ValueError("%s is already registered" % name)

    _modifiers[name] = value


def add_regex(name, value):
    if not isinstance(value, RE_MATCH_TYPE):
        raise TypeError("%r is not a match regep" % value)
    if name in _regexs:
        raise ValueError("%s is already registered" % name)

    _regexs[name] = value


def add_validator(validator, base_tag, tag=None):
    """
    Add a validator for the given tag, which defines a subset of base_tag.
    If tag is None, it is automatically constructed as
    u'!~' + validator.__name__
    Validator is a function that accepts a document node (in the form of a
    Python object), a schema node (also a Python object) and a tracing
    object, and returns True if the document node is valid according to the
    schema node.  Note that the validator function does not have to recurse
    in sub-nodes, because XYS already does it.
    """
    if not tag:
        tag = u'!~' + validator.__name__

    for xid, opts in iteritems(_VALIDATOR_MODES):
        mtag = "%s%s" % (tag, xid)

        SchemaLoader.add_constructor(mtag,
                             ConstructorValidatorNode(mtag,
                                                     base_tag,
                                                     validator,
                                                     opts['name'],
                                                     opts['min'],
                                                     opts['max']))


def add_parameterized_validator(param_validator, base_tag, tag_prefix=None):
    """
    Add a parameterized validator for the given tag prefix.
    If tag_prefix is None, it is automatically constructed as
    u'!~%s(' % param_validator.__name__
    A parametrized validator is a function that accepts a document node
    (in the form of a Python object), a schema node (also a Python
    object), and other parameters (integer or string) that directly come
    from its complete YAML name in the schema.  It returns True if the
    document node is valid according to the schema node.  Note that the
    validator function does not have to recurse in sub-nodes, because
    XYS already does that.
    """
    # pylint: disable-msg=C0111,W0621
    if not tag_prefix:
        tag_prefix = u'!~%s(' % param_validator.__name__
    def multi_constructor(loader, tag_suffix, node):
        params = _split_params(tag_prefix, tag_suffix,
                               numeric=param_validator not in (enum, ienum))
        def temp_validator(node, schema):
            return param_validator(node, schema, *params)
        temp_validator.__name__ = str(tag_prefix + tag_suffix)
        return ConstructorValidatorNode(base_tag,
                                       base_tag,
                                       temp_validator)(loader, node)

    SchemaLoader.add_multi_constructor(tag_prefix, multi_constructor)


def _add_validator_internal(validator, base_tag):
    "with builtin tag prefixing"
    add_validator(validator, base_tag, tag = u'!~~' + validator.__name__)


def _add_parameterized_validator_internal(param_validator, base_tag):
    "with builtin tag prefixing"
    add_parameterized_validator(param_validator, base_tag, tag_prefix=u'!~~%s(' % param_validator.__name__)


def enum(nstr, schema, *symbols): # pylint: disable-msg=W0613
    """
    !~~enum(symb1[,symb2[,...]])
        corresponding strings in documents must be in the set of
        given symbols.
    """
    return nstr in tuple(text_type(symbol) for symbol in symbols)


def ienum(nstr, schema, *symbols): # pylint: disable-msg=W0613
    """
    !~~ienum(symb1[,symb2[,...]])
    Like enum but case insensitive
    """
    return nstr.lower() in (text_type(symbol).lower() for symbol in symbols)


def seqlen(lst, schema, min_len, max_len): # pylint: disable-msg=W0613
    """
    !~~seqlen(min,max)
        corresponding sequences in documents must have a length between
        min and max, included.
    """
    return min_len <= len(lst) <= max_len


def between(val, schema, min_val, max_val): # pylint: disable-msg=W0613
    """
    !~~between(min,max)
        corresponding integers in documents must be between min and max,
        included.
    """
    return min_val <= val <= max_val


def fixed(nstr, schema):
    """
    !~~fixedStr
    !~~fixedInt
        nst == schema
    """
    return nstr == schema


def startswith(nstr, schema):
    """
    !~~startswith
        corresponding strings in documents must begin with the
        associated string in the schema.
    """
    return nstr.startswith(schema)


def prefixedDec(nstr, schema):
    """
    !~~prefixedDec
        corresponding strings in documents must begin with the
        associated string in the schema, and the right part of strings
        in documents must be decimal.
    """
    if not nstr.startswith(schema):
        return False
    postfix = nstr[len(schema):]
    try:
        int(postfix)
    except ValueError:
        return False
    return True


def isBool(nstr, schema): # pylint: disable=unused-argument
    """
    !~~isBool
        '0', '1', False, True
    """
    return nstr in ('0', '1', False, True)


def isFloat(nstr, schema): # pylint: disable=unused-argument
    """
    !~~isFloat
    """
    if isinstance(nstr, (float, integer_types)):
        return True

    if not isinstance(nstr, string_types):
        return False

    try:
        float(nstr)
    except ValueError:
        return False

    return True


def digit(nstr, schema): # pylint: disable=unused-argument
    """
    !~~digit
        '0123456789'.isdigit() or 123456789
    """
    if isinstance(nstr, int):
        nstr = str(nstr)
    elif not isinstance(nstr, string_types):
        return False

    return nstr.isdigit()


def uint(nstr, schema): # pylint: disable=unused-argument
    """
    !~~uint
    """
    if isinstance(nstr, string_types):
        if not nstr.isdigit():
            return False
        try:
            nstr = int(nstr)
        except ValueError:
            return False
    elif not isinstance(nstr, integer_types):
        return False

    return nstr > 0


def callback(val, schema, name = None): # pylint: disable-msg=W0613
    """
    !~~callback(function)
    """
    if name is None:
        name = schema

    if name not in _callbacks:
        return False

    return _callbacks[name](val)


def isIn(val, schema, name = None): # pylint: disable-msg=W0613
    """
    !~~isIn(data)
    """
    if name is None:
        name = schema

    if name not in _lists:
        return False

    try:
        return val in _lists[name]
    except TypeError:
        return False


def regex(val, schema, name = None): # pylint: disable-msg=W0613
    """
    !~~regex(regex) or !~~regex regex
    """
    if name is None:
        name = schema

    if name not in _regexs:
        return False

    try:
        if _regexs[name](val):
            return True
    except TypeError:
        pass

    return False


_add_parameterized_validator_internal(seqlen, u'!!seq')
_add_parameterized_validator_internal(between, u'!!int')
_add_parameterized_validator_internal(enum, u'!!str')
_add_parameterized_validator_internal(ienum, u'!!str')
add_validator(fixed, u'!!str', '!~~fixedStr')
add_validator(fixed, u'!!int', '!~~fixedInt') # XXX: validation tag overloading?
_add_validator_internal(startswith, u'!!str')
_add_validator_internal(prefixedDec, u'!!str')
_add_validator_internal(isBool, u'!!scalar')
_add_validator_internal(isFloat, u'!!scalar')
_add_validator_internal(digit, u'!!scalar')
_add_validator_internal(uint, u'!!scalar')
_add_validator_internal(callback, u'!!str')
_add_validator_internal(isIn, u'!!str')
_add_validator_internal(regex, u'!!str')
_add_parameterized_validator_internal(callback, u'!!any')
_add_parameterized_validator_internal(isIn, u'!!scalar')
_add_parameterized_validator_internal(regex, u'!!scalar')


def _qualify_map(key, content):
    """
    When a dictionary key is optional/optionalnull/mandatory, its corresponding
    _value_ is decorated in an Optional/OptionalNull/Mandatory tuple.
    This function undo the decoration when necessary.
    """
    if not isinstance(key, string_types):
        return key, content

    min_len  = None
    max_len  = None
    modifier = []
    m        = RE_MATCH_CSTR(key)

    if not m:
        raise KeyError("unable to parse, invalid key: %r" % key)

    if m.group(3) is not None:
        min_len = max_len = int(m.group(3))
    elif m.group(4) is not None:
        if m.group(4):
            min_len = int(m.group(4))
        else:
            min_len = 0
        if m.group(5):
            max_len = int(m.group(5))
    elif m.group(6) == '*':
        min_len = 0
    elif m.group(6) == '+':
        min_len = 1
    elif m.group(6) == '?':
        min_len = 0
        max_len = 1

    if min_len is not None and max_len is not None and min_len > max_len:
        raise ValueError('Invalid XYS field length bounds')

    if m.group(7):
        modifier = m.group(7).split(',')

    if m.group(8) == '-':
        modifier.append('strip')

    if m.group(2) == '*':
        return m.group(1), OptionalNull(content, min_len, max_len, modifier)

    if m.group(2) == '?':
        return m.group(1), Optional(content, min_len, max_len, modifier)

    if m.group(2) == '+':
        return m.group(1), Mandatory(content, min_len, max_len, modifier)

    return m.group(1), Mandatory(content, min_len, max_len, modifier)


def _transschema(value, active=None):
    """Compile field qualifiers, rejecting cycles and normalized duplicates."""
    if not isinstance(value, (tuple, dict, list)):
        return value
    if active is None:
        active = set()
    marker = id(value)
    if marker in active:
        raise ValueError('Recursive XYS schemas are not supported')
    active.add(marker)
    try:
        if isinstance(value, tuple):
            return value.__class__(_transschema(value[0], active), *value[1:])
        if isinstance(value, dict):
            result = {}
            for key, val in iteritems(value):
                key, val = _qualify_map(key, _transschema(val, active))
                if key in result:
                    raise ValueError('Duplicate qualified XYS schema key')
                result[key] = val
            return result
        return [_transschema(item, active) for item in value]
    finally:
        active.remove(marker)


def _valid_len(key, value, min_len, max_len):
    if min_len is None:
        return None

    if not hasattr(value, '__len__'):
        LOG.error("unable to test document value length")
        return False

    xlen = len(value)

    if min_len > xlen:
        LOG.error("document value is too short. (min: %s)", min_len)
        return False

    if max_len is not None and max_len < xlen:
        LOG.error("document value is too long. (max: %s)", max_len)
        return False

    return True


def load(src):
    """
    Parse one XYS schema in a stream and produce the corresponding
    internal representation.
    """
    return _transschema(helpers.load_yaml(src, Loader = SchemaLoader))


Nothing = object()

def _validate_node(document, schema, log_qualifier = True):
    if not validate(document, schema.content):
        return False
    if not schema.validator(document, schema.content):
        if log_qualifier:
            LOG.error("document value failed to validate with qualifier %s",
                      schema.validator.__name__)
        return False
    return True

def _apply_modifiers(document, key, value, modifiers):
    """Preserve in-place normalization, calling each modifier exactly once."""
    for name in modifiers:
        if name in _modifiers:
            value = _modifiers[name](value)
        elif hasattr(value, name):
            value = getattr(value, name)()
        document[key] = value
    return value


def _validate_field(document, key, value, schema):
    if not isinstance(schema, (Optional, OptionalNull, Mandatory)):
        return validate(value, schema)
    nullable = isinstance(schema, OptionalNull)
    optional = isinstance(schema, (Optional, OptionalNull))
    if nullable and value is None:
        return True
    # Historical optional-empty semantics are retained, including after modifiers.
    if optional and schema.min_len == 0 and value == '':
        return True
    value = _apply_modifiers(document, key, value, schema.modifier)
    if nullable and value is None:
        return True
    if optional and schema.min_len == 0 and value == '':
        return True
    return (_valid_len(key, value, schema.min_len, schema.max_len) is not False
            and validate(value, schema.content))


def _validate_key_group(document, remaining, key_schema, value_schema):
    matched = []
    for key, value in iteritems(remaining):
        if not validate(key, key_schema, False):
            continue
        if not _validate_field(document, key, value, value_schema):
            return False
        matched.append(key)
    count = len(matched)
    minimum = key_schema.min or 0
    if key_schema.mode == 'mandatory':
        minimum = max(1, minimum)
    if count < minimum or (key_schema.max is not None and count > key_schema.max):
        LOG.error('Invalid number of document keys for qualifier %s',
                  key_schema.validator.__name__)
        return False
    for key in matched:
        del remaining[key]
    return True


def _validate_dict(document, schema):
    if not isinstance(document, dict):
        LOG.error("wanted a dictionary, got a %s", document.__class__.__name__)
        return False
    mandatory, generic, optional = [], [], {}
    for key, value in iteritems(schema):
        if isinstance(key, ValidatorNode):
            target = mandatory if key.mode == 'mandatory' else generic
            target.append((key, value))
        elif isinstance(value, (Optional, OptionalNull)):
            optional[key] = value
        else:
            mandatory.append((key, value))

    remaining = document.copy()
    for key, value_schema in mandatory:
        if isinstance(key, ValidatorNode):
            if not _validate_key_group(document, remaining, key, value_schema):
                return False
            continue
        value = remaining.get(key, Nothing)
        if value is Nothing:
            LOG.error('Missing required document key')
            return False
        if not _validate_field(document, key, value, value_schema):
            return False
        del remaining[key]
    for key, value_schema in generic:
        if not _validate_key_group(document, remaining, key, value_schema):
            return False
    for key, value in iteritems(remaining):
        value_schema = optional.get(key, Nothing)
        if value_schema is Nothing:
            LOG.error('Forbidden document key')
            return False
        if not _validate_field(document, key, value, value_schema):
            return False
    return True


def _validate_list(document, schema):
    if not isinstance(document, list):
        LOG.error("wanted a list, got a %s", document.__class__.__name__)
        return False
    if not schema:
        if document:
            LOG.error('Expected an empty document list')
            return False
        return True
    item_schema = schema[0]
    # Preserve the legacy list-of-mappings shorthand, compiling it once per list.
    if len(schema) > 1 and isinstance(item_schema, dict):
        item_schema = {}
        for part in schema:
            if not isinstance(part, dict):
                raise ValueError('XYS mapping list schemas require mapping entries')
            item_schema.update(part)
    return all(validate(item, item_schema) for item in document)

# TODO: display the document path to errors, and other error message enhancements
# TODO: allow error messages from validators

def validate(document, schema, log_qualifier = True):
    """
    If the document is valid according to the schema, this function returns
    True.
    If the document is not valid according to the schema, errors are logged
    then False is returned.
    """
    if isinstance(schema, ValidatorNode):
        return _validate_node(document, schema, log_qualifier)

    if isinstance(schema, dict):
        return _validate_dict(document, schema)

    if isinstance(schema, list):
        return _validate_list(document, schema)

    if isinstance(schema, Any):
        return True

    if isinstance(schema, Scalar):
        return helpers.is_scalar(document)

    # scalar
    if isinstance(schema, text_type):
        schema = ensure_text(schema)
    if isinstance(document, text_type):
        document = ensure_text(document, 'utf8')
    if schema.__class__ != document.__class__:
        LOG.error("wanted a %s, got a %s",
                  schema.__class__.__name__,
                  document.__class__.__name__)
        return False
    return True


__all__ = [
    'validate',
    'load',
    'seqlen',
    'between',
    'startswith',
    'prefixedDec',
    'isBool',
    'isFloat',
    'digit',
    'uint',
    'callback',
    'isIn',
    'regex',
    'add_callback',
    'add_list',
    'add_modifier',
    'add_regex',
    'add_validator',
    'add_parameterized_validator',
    'ValidatorNode',
    'Optional',
    'OptionalNull',
    'Mandatory',
]
