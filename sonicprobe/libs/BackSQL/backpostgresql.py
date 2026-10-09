# -*- coding: utf8 -*-
# Copyright 2007-2019 The Wazo Authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""sonicprobe.libs.BackSQL.backpostgresql

Backend support for PostgreSQL for anysql

Copyright (C) 2010  Avencall

"""

from six import iterkeys

import psycopg2
import psycopg2.extensions

from sonicprobe.libs import anysql, sqltls
from sonicprobe.libs.urisup import AUTHORITY, PATH, QUERY, uri_help_split

ACCESS_MODE_OPTIONS = {
    'ro': '-c default_transaction_read_only=on',
    'rw': '-c default_transaction_read_only=off',
    'rwc': '-c default_transaction_read_only=off',
}

psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)

__typemap = {
    'host': str,
    'user': str,
    'passwd': str,
    'db': str,
    'port': int,
    'unix_socket': str,
    'compress': bool,
    'connect_timeout': int,
    'read_default_file': str,
    'read_default_group': str,
    'use_unicode': (lambda x: bool(int(x))),
    'conv': None,
    'quote_conv': None,
    'cursorclass': None,
    'charset': str,
}

def __apply_types(params, typemap):
    for k in iterkeys(typemap):
        if k in params:
            if typemap[k] is not None:
                params[k] = typemap[k](params[k])
            else:
                del params[k]

def __dict_from_query(query):
    if not query:
        return {}
    return dict(query)

def connect_by_uri(uri):
    """General URI syntax:

    postgresql://user:passwd@host:port/db

    NOTE: the authority and the path parts of the URI have precedence
    over the query part, if an argument is given in both.

        conv,quote_conv,cursorclass
    are not (yet?) allowed as complex Python objects are needed, hard to
    transmit within an URI...
    """
    puri = uri_help_split(uri)
    mode = anysql._connection_mode(puri[QUERY], ACCESS_MODE_OPTIONS)
    tls = sqltls.configuration(puri[QUERY], puri[AUTHORITY][2] if puri[AUTHORITY] else None, 'postgresql')
    #params = __dict_from_query(puri[QUERY])
    params = {}
    if mode is not None:
        params['options'] = ACCESS_MODE_OPTIONS[mode]
    if tls is not None:
        params.update(sslmode='verify-full', sslrootcert=tls['tls_ca'])
        if 'tls_cert' in tls:
            params.update(sslcert=tls['tls_cert'], sslkey=tls['tls_key'])

    if puri[AUTHORITY]:
        user, passwd, host, port = puri[AUTHORITY]
        if user:
            params['user'] = user
        if passwd:
            params['password'] = passwd
        if host:
            params['host'] = host
        if port:
            params['port'] = port
    if puri[PATH]:
        params['database'] = puri[PATH]
        if params['database'] and params['database'][0] == '/':
            params['database'] = params['database'][1:]

    #__apply_types(params, __typemap)

    conn = psycopg2.connect(**params)
    if tls is not None:
        try:
            if not conn.info.ssl_in_use:
                raise ValueError('SQL TLS was not negotiated')
        except BaseException:
            conn.close()
            raise
    return conn

def escape(s):
    return '.'.join(['"%s"' % comp.replace('"', '""') for comp in s.split('.')])

def cast(fieldname, xtype):
    return "%s::%s" % (fieldname, xtype)

def is_connected(connection, link = None): # pylint: disable=unused-argument
    return connection.status in (psycopg2.extensions.STATUS_READY,
                                 psycopg2.extensions.STATUS_BEGIN,
                                 psycopg2.extensions.STATUS_IN_TRANSACTION)


anysql.register_uri_backend('postgresql', connect_by_uri, psycopg2, None, escape, cast, is_connected)
