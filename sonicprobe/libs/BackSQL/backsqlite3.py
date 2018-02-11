# -*- coding: utf8 -*-
"""Backend support for SQLite3 for anysql

Copyright (C) 2007-2010  Proformatique

"""

__version__ = "$Revision: 7836 $ $Date: 2010-03-31 11:28:11 +0200 (Wed, 31 Mar 2010) $"
__license__ = """
    Copyright (C) 2007-2010  Proformatique

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import sqlite3
import os.path

from sonicprobe.libs import anysql
from sonicprobe.libs import urisup
from sonicprobe.libs.urisup import SCHEME, AUTHORITY, PATH, QUERY, FRAGMENT, uri_help_split, uri_help_unsplit

def __dict_from_query(query):
    if not query:
        return {}
    return dict(query)

def connect_by_uri(uri):
    puri = urisup.uri_help_split(uri)
    opts = __dict_from_query(puri[QUERY])

    con = None
    if "timeout_ms" in opts:
        con = sqlite3.connect(puri[PATH], float(opts["timeout_ms"]))
    else:
        con = sqlite3.connect(puri[PATH])

    return con

def c14n_uri(uri):
    puri = list(urisup.uri_help_split(uri))
    puri[PATH] = os.path.abspath(puri[PATH])
    return uri_help_unsplit(tuple(puri))

def escape(s):
    return '.'.join([('"%s"' % comp.replace('"', '""')) for comp in s.split('.')])

def is_connected(connection, cursor = None):
    _cursor = None
    ret     = True

    try:
        if cursor:
            if isinstance(cursor, anysql.cursor):
                _cursor = cursor._cursor__dbapi2_cursor
            else:
                _cursor = cursor
        else:
            _cursor = connection.cursor()
        _cursor.execute("SELECT 1")
    except sqlite3.ProgrammingError, e:
        ret     = False
    finally:
        if not cursor and _cursor:
            _cursor.close()

    return ret

anysql.register_uri_backend('sqlite3', connect_by_uri, sqlite3, c14n_uri, escape, None, is_connected)
