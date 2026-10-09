# -*- coding: utf-8 -*-
# Copyright 2007-2019 The Wazo Authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""sonicprobe.libs.BackSQL.backsqlite3

Backend support for SQLite3 for anysql

Copyright (C) 2007-2010  Proformatique

"""

import sqlite3
import os.path
import sys

from sonicprobe.libs import anysql
from sonicprobe.libs.urisup import PATH, QUERY, uri_help_split, uri_help_unsplit

OPEN_MODES = frozenset(('ro', 'rw', 'rwc'))
URI_MODES_SUPPORTED = sys.version_info >= (3, 4) and sqlite3.sqlite_version_info >= (3, 7, 7)

def __dict_from_query(query):
    if not query:
        return {}
    return dict(query)

def connect_by_uri(uri):
    puri = uri_help_split(uri)
    opts = __dict_from_query(puri[QUERY])

    mode = anysql._connection_mode(puri[QUERY], OPEN_MODES)
    if mode is not None:
        if not puri[PATH] or puri[PATH] == ':memory:':
            raise ValueError('SQLite open modes require a file path')
        if not URI_MODES_SUPPORTED:
            raise NotImplementedError('SQLite open modes require Python 3.4+ and SQLite 3.7.7+')
        # Imported only for explicit modes: the default path still supports Python 2.
        from pathlib import Path
        database = Path(puri[PATH]).absolute().as_uri() + '?mode=' + mode
        kwargs = {'uri': True}
        thread_options = [value for key, value in puri[QUERY] if key == 'check_same_thread']
        if thread_options:
            if len(thread_options) != 1 or thread_options[0] not in ('true', 'false'):
                raise ValueError('invalid SQLite thread check option')
            kwargs['check_same_thread'] = thread_options[0] == 'true'
        if 'timeout_ms' in opts:
            kwargs['timeout'] = float(opts['timeout_ms']) / 1000.0
        return sqlite3.connect(database, **kwargs)

    # Keep the historical call unchanged, including creation and :memory: behavior.
    con = None
    if 'timeout_ms' in opts:
        con = sqlite3.connect(puri[PATH], float(opts['timeout_ms']) / 1000.0)
    else:
        con = sqlite3.connect(puri[PATH])

    return con

def c14n_uri(uri):
    puri = list(uri_help_split(uri))
    if puri[PATH] == ':memory:':
        return uri_help_unsplit(tuple(puri))
    puri[PATH] = os.path.abspath(puri[PATH])
    return uri_help_unsplit(tuple(puri))

def escape(s):
    return '.'.join([('"%s"' % comp.replace('"', '""')) for comp in s.split('.')])

def is_connected(connection, link = None):
    _cursor = None
    ret     = True

    try:
        if link:
            if isinstance(link, anysql.cursor):
                _cursor = link._cursor__dbapi2_cursor
            else:
                _cursor = link
        else:
            _cursor = connection.cursor()
        _cursor.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        ret = False
    finally:
        if not link and _cursor:
            _cursor.close()

    return ret

anysql.register_uri_backend('sqlite3', connect_by_uri, sqlite3, c14n_uri, escape, None, is_connected)
