# -*- coding: utf-8 -*-
import copy
import unittest

from sonicprobe.libs.argpolicy import (ArgsPolicy, EnvPolicy, PolicyError,
                                       ValidationError, validate_args, validate_env)


class ArgPolicyTests(unittest.TestCase):
    def test_default_denies_nonempty_inputs(self):
        self.assertEqual(validate_args([]), [])
        self.assertEqual(validate_env({}), {})
        self.assertRaises(ValidationError, validate_args, ['--month', 'x'])
        self.assertRaises(ValidationError, validate_env, {'TZ': 'UTC'})

    def test_true_keeps_literal_positionals_and_order(self):
        args = ['a', '--', '-v', '{secret}', '--month=x', '--month', 'y']
        self.assertIs(validate_args(args, True), args)
        env = {'TZ': 'UTC'}
        self.assertIs(validate_env(env, True), env)

    def test_simple_name_accepts_any_single_value(self):
        for args in (['--month', 'anything'], ['--month='], ['--month', '-1']):
            self.assertIs(validate_args(args, ['month']), args)
        self.assertRaises(ValidationError, validate_args, ['--year', '2026'], ['month'])
        self.assertRaises(ValidationError, validate_args, ['month', 'x'], ['month'])

    def test_exact_long_and_short_names(self):
        self.assertEqual(validate_args(['-m', 'x'], ['-m']), ['-m', 'x'])
        for args in (['-mx'], ['--mon', 'x'], ['-month', 'x']):
            self.assertRaises(ValidationError, validate_args, args, ['month', '-m'])

    def test_regex_fullmatch_and_no_mutation(self):
        policy = {'month': {'regex': r'20[0-9]{2}-(0[1-9]|1[0-2])'}}
        original = copy.deepcopy(policy)
        args = ['--month', '2026-10']
        self.assertIs(validate_args(args, policy), args)
        self.assertEqual(policy, original)
        for value in ('2026-13', '2026-10\n', 'prefix2026-10', '2026-10suffix'):
            self.assertRaises(ValidationError, validate_args, ['--month', value], policy)

    def test_shorthand_regex_and_mixed_list(self):
        policy = ['month', {'format': {'choices': ['pdf', 'csv']}}]
        validate_args(['--month', 'anything', '--format=pdf'], policy)
        validate_args(['--month=2026-10'], {'month': r'\d{4}-\d{2}'})
        self.assertRaises(ValidationError, validate_args, ['--format', 'xml'], policy)

    def test_value_count_and_flags(self):
        policy = {'verbose': {'nargs': 0}, 'pair': {'nargs': 2}}
        validate_args(['--verbose', '--pair', 'one', 'two'], policy)
        for args in (['--verbose=yes'], ['--pair', 'one'], ['--pair', 'one', '--verbose'],
                     ['--verbose', 'extra'], ['--pair', 'a', 'b', 'c']):
            self.assertRaises(ValidationError, validate_args, args, policy)

    def test_multiple_values_and_repetition_preserve_tokens(self):
        policy = {'month': {'nargs': '+', 'repeatable': True, 'regex': r'\d{4}-\d{2}'},
                  'verbose': {'nargs': 0}}
        args = ['--month=2026-09', '2026-10', '--verbose', '--month', '2026-11']
        self.assertIs(validate_args(args, policy), args)
        self.assertRaises(ValidationError, validate_args, args + ['bad'], policy)
        validate_args(['--month', '--verbose'], {'month': {'nargs': '*'}, 'verbose': {'nargs': 0}})
        self.assertRaises(ValidationError, validate_args, ['--month'], {'month': {'nargs': '+'}})

    def test_duplicate_options_rejected_by_default(self):
        self.assertRaises(ValidationError, validate_args, ['--month=x', '--month=y'], ['month'])

    def test_deny_takes_precedence(self):
        for allow in (True, ['month'], {'month': {'regex': '.*'}}):
            self.assertRaises(ValidationError, validate_args, ['--month=x'], allow, ['month'])
            self.assertRaises(ValidationError, validate_args, ['--month=x'], allow, True)
        self.assertRaises(ValidationError, validate_env, {'TZ': 'UTC'}, True, ['TZ'])

    def test_unknown_options_not_consumed_as_values(self):
        for args in (['--month', '--evil'], ['--month', '-x'], ['--month', '--'], ['--month', 'x', '--evil']):
            self.assertRaises(ValidationError, validate_args, args, ['month'])
        validate_args(['--month=--literal'], ['month'])

    def test_unrestricted_deny_rejects_short_clusters(self):
        self.assertRaises(ValidationError, validate_args, ['-vf'], True, ['-f'])
        self.assertRaises(ValidationError, validate_args, ['-fpath'], True, ['-f'])
        validate_args(['--', '--month'], True, ['month'])

    def test_invalid_configuration_is_not_a_bypass(self):
        for allow in (None, 'true', 1, ['month', '--month'], {'month': {'regex': '['}},
                      {'month': {'nargs': True}}, {'month': {'nargs': -1}},
                      {'month': {'repeatable': 'yes'}}, {'month': {'unknown': 1}},
                      {'month': {'choices': [1]}}, {'month': {'nargs': 0, 'regex': '.*'}},
                      {'month': False}, ['--'], ['-bad.name']):
            self.assertRaises(PolicyError, ArgsPolicy, allow)
        self.assertRaises(PolicyError, EnvPolicy, {'TZ': {'nargs': 1}})
        self.assertRaises(PolicyError, ArgsPolicy, True, {'month': {}})

    def test_invalid_inputs_rejected_even_with_allow_all(self):
        for args in ('--month', [None], ['x\x00y'], ['x' * 65537]):
            self.assertRaises(ValidationError, validate_args, args, True)
        for env in ([], {'BAD=KEY': 'x'}, {'TZ': None}, {'TZ': 'x\x00y'}):
            self.assertRaises(ValidationError, validate_env, env, True)

    def test_environment_validation(self):
        policy = {'TZ': {'choices': ['UTC', 'Europe/Paris']}, 'MONTH': r'\d{4}-\d{2}'}
        env = {'TZ': 'UTC', 'MONTH': '2026-10'}
        self.assertIs(validate_env(env, policy), env)
        self.assertRaises(ValidationError, validate_env, {'TZ': 'Moon'}, policy)
        self.assertRaises(ValidationError, validate_env, {'SECRET': 'hidden'}, policy)

    def test_errors_never_include_values(self):
        try:
            validate_env({'TOKEN': 'private-value'}, {'TOKEN': 'allowed'})
        except ValidationError as error:
            self.assertNotIn('private-value', str(error))
        else:
            self.fail('invalid value accepted')

    def test_expensive_regex_is_bounded(self):
        policy = ArgsPolicy({'value': {'regex': r'(a+)+$'}})
        self.assertRaises(ValidationError, policy.validate, ['--value', 'a' * 60000 + '!'])

    def test_compiled_rules_do_not_follow_caller_mutation(self):
        spec = {'format': {'choices': ['pdf']}}
        policy = ArgsPolicy(spec)
        spec['format']['choices'].append('exe')
        self.assertRaises(ValidationError, policy.validate, ['--format=exe'])
