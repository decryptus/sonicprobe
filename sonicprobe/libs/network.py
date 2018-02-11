# -*- coding: utf-8 -*-

# Copyright (C) 2015 doowan
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>


import re
import socket
import struct


HEXDIG                  = "0123456789abcdefABCDEF"
BYTES_VAL               = ''.join(map(chr, range(0, 256)))

ATOM                    = '\!#\$%&\'\*\+\-\/0-9\=\?A-Z\^_`a-z\{\|\}~'
QTEXT                   = '\\x20\\x21\\x23-\\x5B\\x5D-\\x7E'
QUOTEDPAIR              = '\(\)\<\>\[\]\:;@\\\,\."'

DOMAIN_PART             = '[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'

MASK_IPV4_DOTDEC        = 1
MASK_IPV4               = 2
MASK_IPV6               = 4
MASK_DOMAIN             = 256
MASK_DOMAIN_TLD         = 512
MASK_DOMAIN_IDN         = 1024

MASK_IP_ALL             = (MASK_IPV4 |
                           MASK_IPV6)

MASK_DOMAIN_ALL         = (MASK_DOMAIN |
                           MASK_DOMAIN_TLD |
                           MASK_DOMAIN_IDN)

MASK_HOST_ALL           = (MASK_IP_ALL |
                           MASK_DOMAIN_ALL)

MASK_EMAIL_HOST_ALL     = (MASK_DOMAIN_TLD |
                           MASK_DOMAIN_IDN)

RE_DOMAIN_PART          = re.compile('^(' + DOMAIN_PART + ')$').match
RE_DOMAIN               = re.compile('^(?:' + DOMAIN_PART + '\.)*(?:' + DOMAIN_PART + ')$').match
RE_DOMAIN_TLD           = re.compile('^(?:' + DOMAIN_PART + '\.)+(?:' + DOMAIN_PART + ')$').match
RE_EMAIL_LOCALPART      = re.compile('^(?:[' + ATOM + ']+(?:\.[' + ATOM + ']+)*|' + \
                                         '"(?:[' + QTEXT + ']|' + \
                                             '\\\[' + QUOTEDPAIR + '])+")$').match
RE_MAC_ADDR_NORMALIZE   = re.compile('([A-F0-9]{1,2})[-: ]?', re.I).findall
RE_MAC_ADDRESS          = re.compile('^([A-F0-9]{2}:){5}([A-F0-9]{2})$', re.I).match


def __all_in(s, charset):
    if not isinstance(s, unicode):
        s = str(s)
    else:
        s = s.encode('utf8')
    return not s.translate(BYTES_VAL, charset)

def __split_sz(s, n):
    return [s[b:b + n] for b in range(0, len(s), n)]

def ipv4_to_long(addr):
    return struct.unpack('!L', socket.inet_aton(addr))[0]

def long_to_ipv4(addr):
    return socket.inet_ntoa(struct.pack('!L', addr))

def normalize_ipv4_dotdec(addr):
    try:
        return socket.inet_ntoa(socket.inet_aton(addr))
    except socket.error:
        return False

def valid_bitmask_ipv4(bit):
    if isinstance(bit, (int, long)):
        bit = str(bit)

    if not isinstance(bit, basestring):
        return False

    return bit.isdigit() and 0 < int(bit) < 33

def bitmask_to_netmask_ipv4(bit):
    if not valid_bitmask_ipv4(bit):
        return False

    return long_to_ipv4((0xFFFFFFFF >> (32 - int(bit))) << (32 - int(bit)))

def valid_ipv4(addr):
    "True <=> valid"
    try:
        socket.inet_aton(addr)
        return True
    except socket.error:
        return False

def valid_ipv4_dotdec(potential_ipv4):
    if not isinstance(potential_ipv4, basestring):
        return False

    if potential_ipv4[0] not in (HEXDIG + "xX") \
       or not __all_in(potential_ipv4[1:], (HEXDIG + ".xX")):
        return False

    s_ipv4 = potential_ipv4.split('.', 4)
    if len(s_ipv4) != 4:
        return False

    try:
        for s in s_ipv4:
            if not 0 <= int(s, 0) <= 255:
                return False
    except ValueError:
        return False

    return True

def valid_ipv6_h16(h16):
    try:
        i = int(h16, 16)
        return 0 <= i <= 65535
    except ValueError:
        return False

def valid_ipv6_right(right_v6):
    if not isinstance(right_v6, basestring):
        return False

    if right_v6 == '':
        return 0

    array_v6 = right_v6.split(':', 8)
    if len(array_v6) > 8 \
       or (len(array_v6) > 7 and ('.' in right_v6)) \
       or (not __all_in(''.join(array_v6[:-1]), HEXDIG)):
        return False

    if '.' in array_v6[-1]:
        if not valid_ipv4_dotdec(array_v6[-1]):
            return False
        h16_count = 2
        array_v6 = array_v6[:-1]
    else:
        h16_count = 0

    for h16 in array_v6:
        if not valid_ipv6_h16(h16):
            return False

    return h16_count + len(array_v6)

def valid_ipv6_left(left_v6):
    if not isinstance(right_v6, basestring):
        return False

    if left_v6 == '':
        return 0

    array_v6 = left_v6.split(':', 7)
    if len(array_v6) > 7 \
       or (not __all_in(''.join(array_v6), HEXDIG)):
        return False

    for h16 in array_v6:
        if not __valid_h16(h16):
            return False

    return len(array_v6)

def valid_ipv6_address(potential_ipv6):
    if not isinstance(potential_ipv6, basestring):
        return False

    sep_pos     = potential_ipv6.find("::")
    sep_count   = potential_ipv6.count("::")

    if sep_pos < 0:
        return valid_ipv6_right(potential_ipv6) == 8
    elif sep_count == 1:
        right = valid_ipv6_right(potential_ipv6[sep_pos + 2:])
        if right is False:
            return False

        left = valid_ipv6_left(potential_ipv6[:sep_pos])
        if left is False:
            return False

        return right + left <= 7
    else:
        return False

def parse_ipv4_cidr(cidr):
    if not isinstance(cidr, basestring):
        return False

    r   = cidr.split('/', 1)
    return r

    if len(r) == 1:
        r.append(32)

    return not valid_ipv4_dotdec(r[0]) or not valid_bitmask_ipv4(r[1])

def encode_idn(value):
    if not isinstance(value, basestring):
        return False

    if not isinstance(value, unicode):
        value = value.decode('utf8')

    return value.encode('idna')

def decode_idn(value):
    if not isinstance(value, basestring):
        return False

    return value.decode('idna')

def valid_domain_part(domain_part):
    if isinstance(domain_part, basestring) \
       and RE_DOMAIN_PART(domain_part):
        return True

    return False

def valid_domain(domain):
    if isinstance(domain, basestring) \
       and len(domain) < 256 \
       and RE_DOMAIN(domain):
        return True

    return False

def valid_domain_tld(domain_tld):
    if isinstance(domain_tld, basestring) \
       and len(domain_tld) < 256 \
       and RE_DOMAIN_TLD(domain_tld):
        return True

    return False

def valid_host(host, host_mask = MASK_HOST_ALL):
    if host_mask & MASK_IPV4 and valid_ipv4(host):
        return True

    if host_mask & MASK_IPV4_DOTDEC and valid_ipv4_dotdec(host):
        return True

    if host_mask & MASK_IPV6 and valid_ipv6_address(host):
        return True

    if host_mask & MASK_DOMAIN_IDN:
        host = encode_idn(host)

    if host_mask & MASK_DOMAIN and valid_domain(host):
        return True

    if host_mask & MASK_DOMAIN_TLD and valid_domain_tld(host):
        return True

    return False

def valid_port_number(port):
    try:
        i = int(port)
        return 0 <= i <= 65535
    except ValueError:
        return False

def valid_email_localpart(localpart):
    if isinstance(localpart, basestring) \
       and 1 <= len(localpart) <= 64 \
       and RE_EMAIL_LOCALPART(localpart):
        return True

    return False

def valid_email_address_literal(address, host_mask = MASK_EMAIL_HOST_ALL):
    if not isinstance(address, basestring) or address == '':
        return False

    if address[0] == '[' and address[-1] == ']':
        if address.startswith('[IPv6:'):
            if not host_mask & MASK_IPV6:
                return False

            address = address[6:-1]

            if not valid_ipv6_address(address):
                return False

            return True

        if not host_mask & MASK_IPV4_DOTDEC:
            return False

        address = address[1:-1]

        if not valid_ipv4_dotdec(address):
            return False

        return True

    mask = 0

    if host_mask & MASK_DOMAIN:
        mask = mask | MASK_DOMAIN

    if host_mask & MASK_DOMAIN_TLD:
        mask = mask | MASK_DOMAIN_TLD

    if host_mask & MASK_DOMAIN_IDN:
        mask = mask | MASK_DOMAIN_IDN

    if mask == 0 or not valid_host(address, mask):
        return False

    return True

def valid_email(email, host_mask = MASK_EMAIL_HOST_ALL):
    if not isinstance(email, basestring) \
       or len(email) > 320:
        return False

    pos         = email.rfind('@')
    if pos < 2:
        return False

    localpart   = email[0:pos]
    address     = email[pos + 1:]

    if not valid_email_localpart(localpart) \
       or not valid_email_address_literal(address, host_mask):
        return False

    return True

def normalize_mac_address(macaddr):
    if not isinstance(macaddr, basestring):
        return False

    m = RE_MAC_ADDR_NORMALIZE(macaddr.upper())
    if len(m) != 6:
        return False

    return ':'.join([('%02X' % int(s, 16)) for s in m])

def valid_mac_address(macaddr):
    if isinstance(macaddr, basestring) \
       and RE_MAC_ADDRESS(macaddr) \
       and macaddr != '00:00:00:00:00:00':
        return True

    return False
