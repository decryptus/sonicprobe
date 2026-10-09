# -*- coding: utf-8 -*-
"""Explicit, verified TLS options shared by the optional SQL adapters.

Omitting these options leaves each driver's historical behavior unchanged.
"""
from six import string_types

TLS_KEYS = frozenset(('tls', 'tls_ca', 'tls_cert', 'tls_key'))
TLS_CONFLICTS = frozenset(('host', 'hostaddr', 'unix_socket', 'read_default_file',
                           'read_default_group', 'options', 'service', 'servicefile'))


def configuration(query, host, backend):
    options = {}
    for key, value in query or ():
        if key == 'tls' or key.startswith('tls_'):
            if key not in TLS_KEYS or key in options:
                raise ValueError('invalid SQL TLS options')
            options[key] = value
    if not options:
        return None
    if (options.get('tls') != 'verify-full' or not options.get('tls_ca')
            or any(not isinstance(value, string_types) or not value or '\x00' in value
                   for value in options.values())
            or ('tls_cert' in options) != ('tls_key' in options)
            or not host or '/' in host
            or backend == 'mysql' and host.lower() == 'localhost'):
        raise ValueError('invalid SQL TLS configuration')
    if any(key.startswith('ssl') or key in TLS_CONFLICTS for key, _ in query or ()):
        raise ValueError('conflicting SQL TLS options')
    return options
