# -*- coding: utf-8 -*-
"""Network helper regressions and retained legacy contracts; no network I/O."""
import socket
import unittest
from six import binary_type, text_type
from sonicprobe.libs import network, urisup
try:
    from unittest import mock
except ImportError:
    import mock


_IPV6_VALID = ('::', '::1', '2001:db8::1', '1:2:3:4:5:6:7:8',
               '::ffff:192.0.2.1', '1:2:3:4:5:6:192.0.2.1',
               'ffff:ffff:ffff:ffff:ffff:ffff:255.255.255.255')
_IPV6_INVALID = ('', ':', ':::', '1::2::3', '1:2:3:4:5:6:7',
                 '1:2:3:4:5:6:7:8:9', '1:2:3:4:5:6:7:8::',
                 '::00000', '::+1', '::-0', ':: 1', '::1\n', '::0x1',
                 '::ffff:0x7f.0.0.1', '::ffff:192.000.2.1',
                 '::ffff:256.0.0.1', '[::1]', 'fe80::1%eth0')


class IPv4Tests(unittest.TestCase):
    def test_invalid_inputs_return_false(self):
        for value in ('', None, False, 123, [], {}, '1.2.3.999', '\x00', '1.2.3.4\n', '1.2.3.4 junk'):
            self.assertFalse(network.valid_ipv4(value))
            self.assertFalse(network.valid_ipv4_dotdec(value))
            self.assertFalse(network.normalize_ipv4_dotdec(value))

    def test_legacy_ipv4_notation_is_preserved(self):
        for value in ('127.1', '0x7f000001', '2130706433', '127.0.0.1'):
            self.assertTrue(network.valid_ipv4(value), value)
            self.assertEqual(network.normalize_ipv4_dotdec(value), '127.0.0.1')
        self.assertTrue(network.valid_ipv4_dotdec('0x7f.0.0.1'))
        self.assertFalse(network.valid_ipv4_dotdec('127.1'))

    def test_ipv4_integer_conversion_roundtrip(self):
        for value in ('0.0.0.0', '192.0.2.1', '255.255.255.255'):
            self.assertEqual(network.long_to_ipv4(network.ipv4_to_long(value)), value)

    def test_bitmask_boundaries_and_unicode_digit(self):
        for value in (1, '1', 32, '32'):
            self.assertTrue(network.valid_bitmask_ipv4(value))
        for value in (0, 33, True, None, '', u'\u00b2'):
            self.assertFalse(network.valid_bitmask_ipv4(value))
        self.assertEqual(network.bitmask_to_netmask_ipv4(24), '255.255.255.0')
        self.assertFalse(network.bitmask_to_netmask_ipv4(0))

    def test_cidr_results_and_invalid_empty_inputs(self):
        self.assertEqual(network.parse_ipv4_cidr('192.0.2.1'), ['192.0.2.1', '32'])
        self.assertEqual(network.parse_ipv4_cidr('192.0.2.1/24'), ['192.0.2.1', '24'])
        for value in ('', '/', '/24', '192.0.2.1/', '192.0.2.1/0', '192.0.2.1/33', None):
            self.assertFalse(network.parse_ipv4_cidr(value))


class IPv6Tests(unittest.TestCase):
    def test_valid_addresses(self):
        for value in _IPV6_VALID:
            self.assertTrue(network.valid_ipv6_address(value), value)

    def test_invalid_addresses(self):
        for value in _IPV6_INVALID + (None, True, [], 1):
            self.assertFalse(network.valid_ipv6_address(value), value)

    def test_h16_is_one_to_four_hex_digits(self):
        for value in ('0', '0000', 'ffff', 'ABCD'):
            self.assertTrue(network.valid_ipv6_h16(value))
        for value in ('', '00000', '+1', '-0', ' 1', '1\n', '0x1', u'\uff11', None, 1):
            self.assertFalse(network.valid_ipv6_h16(value))

    def test_fragment_helpers_preserve_counts(self):
        self.assertEqual(network.valid_ipv6_left(''), 0)
        self.assertEqual(network.valid_ipv6_right(''), 0)
        self.assertEqual(network.valid_ipv6_left('1:2:3'), 3)
        self.assertEqual(network.valid_ipv6_right('1:192.0.2.1'), 3)
        self.assertIs(network.valid_ipv6_right('1:2:'), False)
        self.assertIs(network.valid_ipv6_left('1:2:'), False)

    def test_ipv6_matches_system_parser_on_generated_corpus(self):
        corpus = list(_IPV6_VALID + _IPV6_INVALID)
        for index in range(128):
            groups = [format((index * 65521 + n * 8171) % 65536, 'x') for n in range(8)]
            corpus.extend((':'.join(groups), '::' + ':'.join(groups[:index % 8]),
                           ':'.join(groups[:-1] + ['+' + groups[-1]])))
        for value in corpus:
            try:
                socket.inet_pton(socket.AF_INET6, value)
                expected = True
            except socket.error:
                expected = False
            self.assertEqual(network.valid_ipv6_address(value), expected, value)

    def test_uri_ipv6_literals_keep_valid_forms_and_reject_bad_groups(self):
        self.assertTrue(urisup.uri_help_split('http://[2001:db8::1]/'))
        with self.assertRaises(ValueError):
            urisup.uri_help_split('http://[::00000]/')


class DomainTests(unittest.TestCase):
    def test_default_host_and_email_masks_work_with_text(self):
        self.assertTrue(network.valid_host('example.org'))
        self.assertTrue(network.valid_host(u'b\u00fccher.example'))
        self.assertTrue(network.valid_email('reader@example.org'))
        self.assertTrue(network.valid_email(u'reader@b\u00fccher.example'))

    def test_domain_masks_keep_label_count_semantics(self):
        self.assertTrue(network.valid_host('localhost', network.MASK_DOMAIN))
        self.assertFalse(network.valid_host('localhost', network.MASK_DOMAIN_TLD))
        self.assertTrue(network.valid_host('example.org', network.MASK_DOMAIN_TLD))
        self.assertFalse(network.valid_host('example.org', network.MASK_SUB_DOMAIN_TLD))
        self.assertTrue(network.valid_host('www.example.org', network.MASK_SUB_DOMAIN_TLD))
        self.assertFalse(network.valid_host('example.org', network.MASK_DOMAIN_IDN))

    def test_domains_reject_trailing_newline_and_invalid_labels(self):
        for function, value in ((network.valid_domain_part, 'example'),
                                (network.valid_domain, 'example.org'),
                                (network.valid_domain_tld, 'example.org'),
                                (network.valid_sub_domain_tld, 'www.example.org')):
            self.assertTrue(function(value))
            self.assertFalse(function(value + '\n'))
            self.assertFalse(function(None))
        for value in ('-example.org', 'example-.org', 'a..org', 'example.org.', 'a' * 64 + '.org'):
            self.assertFalse(network.valid_domain(value))

    def test_idna_return_types_and_roundtrip(self):
        domain = u'b\u00fccher.example'
        encoded = network.encode_idn(domain)
        self.assertIsInstance(encoded, binary_type)
        self.assertEqual(encoded, b'xn--bcher-kva.example')
        self.assertIsInstance(network.encode_idn(domain, True), text_type)
        self.assertEqual(network.decode_idn(encoded), domain)
        self.assertEqual(network.decode_idn('xn--bcher-kva.example'), domain)
        self.assertEqual(network.decode_idn(domain), domain)

    def test_malformed_idna_does_not_escape_predicates(self):
        for value in ('a..org', 'a' * 64 + '.org', u'\ud800.org', None):
            self.assertFalse(network.encode_idn(value))
            self.assertFalse(network.valid_host(value))
            self.assertFalse(network.valid_domain_cert(value))
        for value in ('xn--', b'\xff', None):
            self.assertFalse(network.decode_idn(value))

    def test_certificate_wildcard_metadata(self):
        for mask in (network.MASK_DOMAIN_ALL, network.MASK_DOMAIN_TLD):
            self.assertEqual(network.parse_domain_cert('www.example.org', mask),
                             {'domain': 'www.example.org', 'wildcard': False})
            self.assertEqual(network.parse_domain_cert('*.example.org', mask),
                             {'domain': 'example.org', 'wildcard': True})
        self.assertEqual(network.parse_domain_cert(u'*.b\u00fccher.example'),
                         {'domain': 'xn--bcher-kva.example', 'wildcard': True})
        for value in ('*example.org', 'www.*.org', '*.*.org', '*.example.org\n'):
            self.assertFalse(network.valid_domain_cert(value))

    def test_ascii_idna_decode_errors_do_not_take_utf8_fallback(self):
        class InvalidLabel(binary_type):
            def decode(self, encoding='utf-8', errors='strict'):
                if encoding == 'idna':
                    raise UnicodeDecodeError('idna', b'xn--', 0, 4, 'invalid label')
                return super(InvalidLabel, self).decode(encoding, errors)
        with mock.patch.object(network, 'ensure_binary', return_value=InvalidLabel(b'xn--')):
            self.assertFalse(network.decode_idn('xn--'))

    def test_certlord_subdomain_policy_is_preserved(self):
        mask = network.MASK_SUB_DOMAIN_TLD
        self.assertTrue(network.valid_domain_cert('www.example.org', mask))
        self.assertTrue(network.valid_domain_cert('*.www.example.org', mask))
        self.assertFalse(network.valid_domain_cert('example.org', mask))
        self.assertFalse(network.valid_domain_cert('*.example.org', mask))
        self.assertFalse(network.valid_domain_cert('www.example.org\n', mask))

    def test_dwho_server_id_and_nsaproxy_trailing_dot_conventions(self):
        self.assertTrue(network.valid_domain('demo-node'))
        self.assertFalse(network.valid_domain('demo-node\n'))
        value = 'example.org.'
        self.assertTrue(network.valid_host(value[:-1], network.MASK_DOMAIN))
        self.assertFalse(network.valid_host(value, network.MASK_DOMAIN))


class EmailPortMacTests(unittest.TestCase):
    def test_one_character_email_and_quoted_localpart(self):
        for value in ('a@example.org', 'ab@example.org', '"a@b"@example.org'):
            self.assertTrue(network.valid_email(value))
        for value in ('@example.org', 'a@', 'a@example.org\n', 'a\n@example.org', None):
            self.assertFalse(network.valid_email(value))
        self.assertFalse(network.valid_email_localpart('abc\n'))

    def test_email_address_literal_masks(self):
        self.assertTrue(network.valid_email('a@[192.0.2.1]', network.MASK_IPV4_DOTDEC))
        self.assertTrue(network.valid_email('a@[IPv6:2001:db8::1]', network.MASK_IPV6))
        self.assertFalse(network.valid_email('a@[IPv6:::00000]', network.MASK_IPV6))
        self.assertFalse(network.valid_email('a@[192.0.2.1]'))
        self.assertFalse(network.valid_email_address_literal('[]', network.MASK_IPV4_DOTDEC))

    def test_ports_reject_fractional_and_non_scalar_values(self):
        for value in (0, 80, '80', 65535, '65535'):
            self.assertTrue(network.valid_port_number(value))
        for value in (-1, 65536, True, False, 80.5, 80.0, float('inf'), None, [], ''):
            self.assertFalse(network.valid_port_number(value))

    def test_mac_normalization_accepts_existing_formats(self):
        for value in ('001122334455', '00:11:22:33:44:55', '00-11-22-33-44-55',
                      '00 11 22 33 44 55', '0011.2233.4455'):
            self.assertEqual(network.normalize_mac_address(value), '00:11:22:33:44:55')
        self.assertEqual(network.normalize_mac_address('a:b:c:d:e:f'), '0A:0B:0C:0D:0E:0F')

    def test_mac_normalization_does_not_discard_garbage(self):
        for value in ('zz00:11:22:33:44:55zz', '00:11:22:33:44:55\n', '00:11:22:33:44', None):
            self.assertFalse(network.normalize_mac_address(value))

    def test_mac_validation_requires_complete_input(self):
        self.assertTrue(network.valid_mac_address('00:11:22:33:44:55'))
        self.assertFalse(network.valid_mac_address('00:11:22:33:44:55\n'))
        self.assertFalse(network.valid_mac_address('00:00:00:00:00:00'))

    def test_predicates_handle_wrong_input_types(self):
        functions = (network.valid_host, network.valid_domain_cert, network.valid_ipv4,
                     network.valid_ipv4_dotdec, network.valid_ipv6_address,
                     network.valid_ipv6_h16, network.valid_port_number,
                     network.valid_email, network.valid_mac_address)
        for function in functions:
            for value in (None, [], {}, object()):
                self.assertFalse(function(value), function.__name__)
