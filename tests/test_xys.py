# -*- coding: utf-8 -*-
"""Compilation, isolation and compatibility of the shared XYS validator."""
import copy
import re
import threading
import unittest
import yaml
from sonicprobe.libs import xys


class SchemaLoadingTests(unittest.TestCase):
    def test_python_tags_are_rejected(self):
        for source in ('!!python/name:builtins.str', '!!python/object/apply:builtins.str [example]'):
            with self.assertRaises(yaml.constructor.ConstructorError):
                xys.load(source)

    def test_schema_tags_do_not_modify_yaml_loaders(self):
        xys.load('value: !!any')
        for loader in (yaml.SafeLoader, yaml.Loader):
            for source in ('!!any', '!~~startswith abc'):
                with self.assertRaises(yaml.constructor.ConstructorError):
                    yaml.load(source, Loader=loader)

    def test_duplicate_explicit_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            xys.load('name: !!str\nname: 0')

    def test_duplicate_qualified_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            xys.load('name: !!str\nname?: 0')

    def test_aliases_and_merge_overrides_still_work(self):
        schema = xys.load('first: &fields {name: !!str }\nsecond: {<<: *fields, name: 0}')
        self.assertTrue(xys.validate({'first': {'name': 'a'}, 'second': {'name': 4}}, schema))

    def test_recursive_schemas_are_rejected(self):
        with self.assertRaises((ValueError, yaml.constructor.ConstructorError)):
            xys.load('&cycle [*cycle]')

    def test_invalid_length_bounds_are_rejected(self):
        for source in ('value![3,1]: !!str', '!~~startswith? (3,1) p: !!str'):
            with self.assertRaises(ValueError):
                xys.load(source)

    def test_constructor_bounds_do_not_leak_between_loads(self):
        limited = xys.load('!~~startswith? (2,3) prefix: !!str')
        plain = xys.load('!~~startswith? prefix: !!str')
        self.assertFalse(xys.validate({}, limited))
        self.assertTrue(xys.validate({}, plain))
        self.assertTrue(xys.validate(dict(('prefix%d' % n, 'v') for n in range(4)), plain))

    def test_constructor_bounds_do_not_leak_between_nodes(self):
        schema = xys.load('!~~startswith? (2,2) a: !!str\n!~~startswith? b: !!str')
        self.assertTrue(xys.validate({'a1': 'x', 'a2': 'x'}, schema))

    def test_constructor_registration_is_reusable_from_threads(self):
        results = []
        def compile_schema(index):
            source = '!~~startswith? (1,1) p: !!str' if index % 2 else '!~~startswith? p: !!str'
            results.append(xys.validate({}, xys.load(source)) == (index % 2 == 0))
        threads = [threading.Thread(target=compile_schema, args=(n,)) for n in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(3)
            self.assertFalse(thread.is_alive())
        self.assertEqual(results, [True] * 20)

    def test_signed_ranges_and_numeric_enum_symbols(self):
        self.assertTrue(xys.validate(-1, xys.load('!~~between(-2,2) 0')))
        self.assertFalse(xys.validate(3, xys.load('!~~between(-2,2) 0')))
        for tag in ('enum', 'ienum'):
            schema = xys.load('!~~%s(01,2foo,OK)' % tag)
            self.assertTrue(xys.validate('01', schema))
            self.assertTrue(xys.validate('2foo', schema))
            self.assertFalse(xys.validate('1', schema))
        self.assertTrue(xys.validate('ok', xys.load('!~~ienum(01,OK)')))

    def test_malformed_parameter_lists_fail_at_load(self):
        for source in ('!~~enum(a,)', '!~~enum(a', '!~~enum()'):
            with self.assertRaises(ValueError):
                xys.load(source)


class DocumentValidationTests(unittest.TestCase):
    def test_required_optional_nullable_and_unknown_fields(self):
        schema = xys.load('name: !!str\nage?: 0\nnote*: !!str')
        for document in ({'name': 'a'}, {'name': 'a', 'age': 3, 'note': None}):
            self.assertTrue(xys.validate(document, schema))
        for document in ({}, {'name': 1}, {'name': 'a', 'age': None}, {'name': 'a', 'other': 1}):
            self.assertFalse(xys.validate(document, schema))

    def test_bool_is_not_an_integer_schema(self):
        self.assertFalse(xys.validate(True, xys.load('!!int 0')))
        self.assertTrue(xys.validate(True, xys.load('!!bool true')))

    def test_empty_list_schema_accepts_only_empty_list(self):
        schema = xys.load('[]')
        self.assertTrue(xys.validate([], schema))
        self.assertFalse(xys.validate([1], schema))
        self.assertFalse(xys.validate({}, schema))

    def test_sequence_items_and_legacy_mapping_shorthand(self):
        schema = xys.load('[{name: !!str }, {"age?": 0}]')
        self.assertTrue(xys.validate([{'name': 'a', 'age': 2}, {'name': 'b'}], schema))
        self.assertFalse(xys.validate([{'name': 'a'}, {'name': 2}], schema))
        self.assertTrue(xys.validate([1, 2], xys.load('[0]')))

    def test_non_string_literal_keys_support_nested_values(self):
        schema = xys.load('1: {name: !!str }\n2: [!!str ]')
        self.assertTrue(xys.validate({1: {'name': 'a'}, 2: ['b']}, schema))
        self.assertFalse(xys.validate({1: {'name': 0}, 2: []}, schema))

    def test_dynamic_key_groups_count_and_validate_values(self):
        schema = xys.load('!~~startswith+ (1,2) p: {value: 0}')
        self.assertTrue(xys.validate({'p1': {'value': 1}}, schema))
        self.assertFalse(xys.validate({}, schema))
        self.assertFalse(xys.validate({'p1': {'value': 'bad'}}, schema))
        self.assertFalse(xys.validate(dict(('p%d' % n, {'value': n}) for n in range(3)), schema))

    def test_length_limits_and_historical_optional_empty(self):
        schema = xys.load('name![1,3]: !!str\nvalue?[0,2]: [0]')
        self.assertTrue(xys.validate({'name': 'abc', 'value': ''}, schema))
        self.assertTrue(xys.validate({'name': 'abc', 'value': [1, 2]}, schema))
        self.assertFalse(xys.validate({'name': '', 'value': []}, schema))
        self.assertFalse(xys.validate({'name': 'abc', 'value': [1, 2, 3]}, schema))

    def test_modifiers_execute_once_and_update_document(self):
        calls = []
        name = 'test_xys_once'
        xys.add_modifier(name, lambda value: calls.append(value) or value + '!')
        self.addCleanup(xys._modifiers.pop, name)
        for suffix in ('', '?', '*'):
            document = {'name': 'a'}
            schema = xys.load('name%s|%s: !!str' % (suffix, name))
            before = len(calls)
            self.assertTrue(xys.validate(document, schema))
            self.assertEqual(document, {'name': 'a!'})
            self.assertEqual(len(calls) - before, 1)

    def test_method_modifiers_and_nullable_results(self):
        schema = xys.load('name|strip,lower: !!str')
        document = {'name': ' NAME '}
        self.assertTrue(xys.validate(document, schema))
        self.assertEqual(document, {'name': 'name'})
        name = 'test_xys_none'
        xys.add_modifier(name, lambda value: None)
        self.addCleanup(xys._modifiers.pop, name)
        self.assertTrue(xys.validate({'name': 'a'}, xys.load('name*|%s: !!str' % name)))

    def test_validation_without_modifiers_preserves_input(self):
        document = {'nested': [{'name': 'a'}]}
        before = copy.deepcopy(document)
        self.assertTrue(xys.validate(document, xys.load('nested: [{name: !!str }]')))
        self.assertEqual(document, before)

    def test_uint_unicode_non_decimal_digit_is_rejected(self):
        self.assertFalse(xys.validate(u'\u00b2', xys.load('!~~uint')))

    def test_extensions_callbacks_lists_and_regex(self):
        name = 'test_xys_extension'
        xys.add_callback(name, lambda value: value == {'ok': True})
        xys.add_list(name, ['a', 'b'])
        xys.add_regex(name, re.compile(r'^item[0-9]+$').match)
        for registry in (xys._callbacks, xys._lists, xys._regexs):
            self.addCleanup(registry.pop, name)
        self.assertTrue(xys.validate({'ok': True}, xys.load('!~~callback(%s)' % name)))
        self.assertFalse(xys.validate({'ok': False}, xys.load('!~~callback(%s)' % name)))
        self.assertTrue(xys.validate('a', xys.load('!~~isIn(%s)' % name)))
        self.assertTrue(xys.validate('item12', xys.load('!~~regex(%s)' % name)))

    def test_custom_validators_and_parameterized_validators(self):
        xys.add_validator(lambda value, schema: value.startswith(schema), '!!str', '!~test_xys_prefix')
        xys.add_parameterized_validator(lambda value, schema, n: value % n == 0,
                                        '!!int', '!~test_xys_multiple(')
        self.assertTrue(xys.validate('prefix', xys.load('!~test_xys_prefix pre')))
        self.assertFalse(xys.validate('bad', xys.load('!~test_xys_prefix pre')))
        self.assertTrue(xys.validate(6, xys.load('!~test_xys_multiple(3) 0')))
        self.assertFalse(xys.validate(7, xys.load('!~test_xys_multiple(3) 0')))
