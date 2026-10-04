"""Preserve public consumer acceptance and rejection contracts."""
import copy
import re
import unittest
from six import string_types
from sonicprobe.libs import network, xys
from xys_consumer_fixtures import SCHEMAS

_CERTIFICATE_ID = '12345678-1234-1234-1234-123456789abc'
_EXAMPLES = {
    'METRICS_QSCHEMA': {'endpoint': 'metrics', 'target': None},
    'PROBES_QSCHEMA': {'endpoint': 'probes', 'target': 'example.org'},
    'SAVE_PSCHEMA': {'domain': 'www.example.org', 'cert': 'c' * 1000, 'key': 'k' * 1000, 'chain': ''},
    'VALIDATE_QSCHEMA': {'sub_domain': 'www.example.org'},
    'UPSERT_QSCHEMA': {'certificate_id': _CERTIFICATE_ID},
    'INDEX_QSCHEMA': {'certificate_id': _CERTIFICATE_ID},
    'UPSERT_PSCHEMA': {'domains': ['www.example.org']},
    'WELL_KNOWN_DELETE_QSCHEMA': {'challenge': 'a' * 43},
    'WELL_KNOWN_GET_QSCHEMA': {'challenge': 'a' * 43},
    'WELL_KNOWN_PUT_QSCHEMA': {'challenge': 'a' * 43},
    'ENDPOINT_GET_QSCHEMA': {'server_id': 'localhost', 'endpoint': 'zones', 'command': 'check'},
    'ENDPOINT_PUT_QSCHEMA': {'server_id': 'localhost', 'endpoint': 'zones', 'id': 'example.org.', 'command': 'notify'},
    'ENDPOINT_POST_QSCHEMA': {'server_id': 'localhost', 'endpoint': 'zones'},
    'ENDPOINT_PATCH_QSCHEMA': {'server_id': 'localhost', 'endpoint': 'zones', 'id': 'example.org.'},
    'ENDPOINT_DELETE_QSCHEMA': {'server_id': 'localhost', 'endpoint': 'zones', 'id': 'example.org.'},
    'ENDPOINT_VALIDATE_QSCHEMA': {'server_id': 'localhost', 'endpoint': 'zones', 'id': 'example.org.'},
    'ENDPOINT_POST_PSCHEMA': {'name': 'example.org.', 'kind': 'PRIMARY', 'nameservers': ['ns.example.org.'], 'masters': ['192.0.2.1']},
    'ENDPOINT_PATCH_PSCHEMA': {'rrsets': [{'name': 'example.org.', 'type': 'A', 'ttl': 300,
        'changetype': 'REPLACE', 'comments': [{'content': 'example', 'account': 'owner'}],
        'records': [{'content': '192.0.2.1', 'disabled': False}]}]},
    'RUN_QSCHEMA': {'endpoint': 'job', 'id': 'example'},
    'RUN_PSCHEMA': {'env': {'EXAMPLE': '1'}, 'envfiles': [], 'args': ['a,b'],
                   'argfiles': [{'arg': '--file', 'filename': 'input', 'content': 'example'}]},
}


def install_extensions():
    # Same domain/address helpers as consumers; UUID callback is represented by
    # its canonical-format contract here, not by importing application runtimes.
    callbacks = {
        'pdns.domain': lambda value: isinstance(value, string_types) and value.endswith('.') and
            network.valid_host(value[:-1], network.MASK_DOMAIN),
        'pdns.ipaddr': lambda value: network.valid_host(value, network.MASK_IPV4_DOTDEC | network.MASK_IPV6),
        'ssl_certs.sub_domain': lambda value: network.valid_domain_cert(value, network.MASK_SUB_DOMAIN_TLD),
        'ssl_certs.certificate_id': lambda value: isinstance(value, string_types) and
            re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z', value) is not None,
    }
    regexes = {'job.envname': re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]{0,63}\Z').match,
               'letsencrypt.challenge': re.compile(r'^[0-9A-Za-z_\-]{43}\Z').match}
    for name, callback in callbacks.items():
        xys.add_callback(name, callback)
    for name, regex in regexes.items():
        xys.add_regex(name, regex)
    return callbacks, regexes


class ConsumerSchemaTests(unittest.TestCase):
    def setUp(self):
        callbacks, regexes = install_extensions()
        for name in callbacks:
            self.addCleanup(xys._callbacks.pop, name)
        for name in regexes:
            self.addCleanup(xys._regexs.pop, name)

    def test_all_twenty_schemas_accept_representative_documents(self):
        self.assertEqual(len(SCHEMAS), 20)
        for repo, path, sha, name, source in SCHEMAS:
            document = copy.deepcopy(_EXAMPLES[name])
            self.assertTrue(xys.validate(document, xys.load(source)), (repo, name))
            self.assertEqual(document, _EXAMPLES[name])

    def test_all_schemas_reject_unknown_keys_and_non_mappings(self):
        for repo, path, sha, name, source in SCHEMAS:
            schema = xys.load(source)
            document = copy.deepcopy(_EXAMPLES[name])
            document['unknown_field'] = 'unexpected'
            self.assertFalse(xys.validate(document, schema), (repo, name))
            self.assertFalse(xys.validate([], schema), (repo, name))

    def test_auton_limits_and_literal_comma(self):
        source = next(row[4] for row in SCHEMAS if row[3] == 'RUN_PSCHEMA')
        schema = xys.load(source)
        for field in ('envfiles', 'args'):
            self.assertTrue(xys.validate({field: ['a,b'] * 64}, schema))
            self.assertFalse(xys.validate({field: ['a,b'] * 65}, schema))
        self.assertTrue(xys.validate({'env': dict(('V%d' % n, 'value') for n in range(64))}, schema))
        self.assertFalse(xys.validate({'env': dict(('V%d' % n, 'value') for n in range(65))}, schema))
        self.assertFalse(xys.validate({'env': {'BAD-NAME': 'value'}}, schema))

    def test_certlord_domain_count_material_lengths_and_challenge(self):
        schemas = dict((row[3], xys.load(row[4])) for row in SCHEMAS if row[0] == 'decryptus/certlord')
        for value in ([], ['example.org', 'other.example.org']):
            self.assertFalse(xys.validate({'domains': value}, schemas['UPSERT_PSCHEMA']))
        document = copy.deepcopy(_EXAMPLES['SAVE_PSCHEMA'])
        document['cert'] = 'c' * 999
        self.assertFalse(xys.validate(document, schemas['SAVE_PSCHEMA']))
        for challenge in ('a' * 42, 'a' * 44, 'a' * 43 + '\n'):
            self.assertFalse(xys.validate({'challenge': challenge}, schemas['WELL_KNOWN_GET_QSCHEMA']))
