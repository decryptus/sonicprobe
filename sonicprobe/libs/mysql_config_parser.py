# -*- coding: utf-8 -*-
# Copyright 2008-2019 Proformatique
# SPDX-License-Identifier: GPL-3.0-or-later
"""sonicprobe.libs.mysql_config_parser"""

import io
import os
import re
import subprocess

# pylint: disable=unused-import
from six.moves.configparser import ConfigParser, Error, NoSectionError, DuplicateSectionError, \
        NoOptionError, InterpolationError, InterpolationMissingOptionError, \
        InterpolationSyntaxError, InterpolationDepthError, ParsingError, \
        MissingSectionHeaderError, _default_dict

from six import PY2, StringIO, ensure_text, string_types

import semantic_version

MYSQL_DEFAULT_HOST     = 'localhost'
MYSQL_DEFAULT_PORT     = 3306

MYSQLCLIENT_PARSE_VERS = re.compile(r'^mysql\s+Ver\s+(?P<version>[^\s]+)\s+Distrib\s+(?P<distrib>[^\s,]+)').match
MYSQLDUMP_PARSE_VERS   = re.compile(r'^mysqldump\s+Ver\s+(?P<version>[^\s]+)\s+Distrib\s+(?P<distrib>[^\s,]+)').match


class MySQLConfigVersion(object):
    def __init__(self, default_file = 'client.cnf', custom_file = "", config_dir = None):
        self._config_dir   = config_dir
        self._default_file = default_file or ""
        self._custom_file  = custom_file or ""
        self._myconf       = MySQLConfigParser()

    def _read_file(self, filepath):
        if self._config_dir and not filepath.startswith(os.path.sep):
            filepath = os.path.join(self._config_dir, filepath)

        if not os.path.isfile(filepath):
            return ""

        with open(filepath, 'r') as f:
            return f.read()

    @staticmethod
    def _set_specific_conf(cfg, section, version):
        secname = "%s=%s" % (section, version)
        if cfg.has_section(secname):
            for x in cfg.items(secname):
                cfg.set(*[section] + list(x))

    def _check_conf_versions(self, cfg, section, version, vername = ""):
        ver = semantic_version.Version(version, partial = True)
        for x in ('major', 'minor', 'patch', 'prerelease', 'build'):
            v = getattr(ver, x, None)
            if v is None or v == ():
                break
            if isinstance(v, tuple):
                v = '.'.join(v)
            vername += "%s." % v
            self._set_specific_conf(cfg, section, vername.rstrip('.'))

    def _get_config(self, section, progpath, parse_vers, check_version = True):
        my_vers = False
        if check_version:
            my_vers = parse_vers(ensure_text(subprocess.check_output((progpath, '--version')),
                                             encoding='ascii', errors='replace').strip())

        # Each request reflects current files; removed options must not survive.
        self._myconf = MySQLConfigParser()
        for filename in (self._default_file, self._custom_file):
            with StringIO(ensure_text(self._read_file(filename))) as myconf:
                self._myconf.read_file(myconf)

        if my_vers:
            self._check_conf_versions(self._myconf,
                                      section,
                                      my_vers.group('version'),
                                      'ver-')
            self._check_conf_versions(self._myconf,
                                      section,
                                      my_vers.group('distrib'),
                                      'dist-')

        return self._myconf

    def get_client(self, check_version = True):
        return self._get_config('client', 'mysql', MYSQLCLIENT_PARSE_VERS, check_version)

    def get_mysqldump(self, check_version = True):
        return self._get_config('mysqldump', 'mysqldump', MYSQLDUMP_PARSE_VERS, check_version)


class MySQLConfigParser(ConfigParser):
    if os.name == 'nt':
        RE_INCLUDE_FILE = re.compile(r'^[^\.]+(?:\.ini|\.cnf)\Z').match
    else:
        RE_INCLUDE_FILE = re.compile(r'^[^\.]+\.cnf\Z').match

    def __init__(self, defaults = None, dict_type = _default_dict, allow_no_value=True):
        ConfigParser.__init__(self, defaults, dict_type, allow_no_value)

    @staticmethod
    def valid_filename(filename):
        if isinstance(filename, string_types) and MySQLConfigParser.RE_INCLUDE_FILE(filename):
            return True

        return False

    def getboolean(self, section, option, retint=False): # pylint: disable=arguments-differ
        ret = ConfigParser.getboolean(self, section, option)

        if not retint:
            return ret

        return int(ret)

    def read(self, filenames, encoding=None): # pylint: disable=arguments-differ
        if isinstance(filenames, string_types):
            filenames = [filenames]

        file_ok = []
        for filename in filenames:
            if not self.valid_filename(os.path.basename(filename)):
                continue
            try:
                stream = io.open(filename, encoding=encoding)
            except IOError:
                continue
            with stream:
                self.read_file(stream, filename)
            file_ok.append(filename)
        return file_ok

    def readfp(self, fp, filename=None):
        return self.read_file(fp, filename)

    def read_file(self, f, source=None):
        if PY2:
            return ConfigParser.readfp(self, MySQLConfigParserFilter(f), source)

        return ConfigParser.read_file(self, MySQLConfigParserFilter(f), source) # pylint: disable=no-member


class MySQLConfigParserFilter(object): # pylint: disable=useless-object-inheritance
    RE_HEADER_OPT  = re.compile(r'^\s*\[[^\]]+\]\s*').match
    RE_INCLUDE_OPT = re.compile(r'^\s*!\s*(?:(include|includedir)\s+(.+))$').match

    MAX_INCLUDE_DEPTH = 64

    def __init__(self, fp, active_paths=()):
        self.fp = fp
        name = getattr(fp, 'name', None)
        path = os.path.realpath(name) if isinstance(name, string_types) else None
        if path and path in active_paths:
            raise ParsingError("Recursive configuration include: %r" % path)
        if len(active_paths) >= self.MAX_INCLUDE_DEPTH:
            raise ParsingError("Configuration include depth exceeded")
        self._active_paths = active_paths + ((path,) if path else ())
        self._iterator = self._iter_lines()

    def __iter__(self):
        return self._iterator

    def readline(self):
        return next(self._iterator, '')

    def _iter_lines(self):
        for line in self.fp:
            sline = line.lstrip()
            if not sline.startswith('!'):
                yield line
                continue
            match = self.RE_INCLUDE_OPT(sline)
            if not match or not match.group(2).strip():
                raise ParsingError("Invalid configuration include directive")
            path = match.group(2).strip()
            if match.group(1) == 'include':
                if not MySQLConfigParser.valid_filename(os.path.basename(path)):
                    raise ParsingError("Wrong filename for include option")
                paths = [path]
            else:
                paths = [os.path.join(path, name) for name in sorted(os.listdir(path))
                         if MySQLConfigParser.valid_filename(name)]
            for filename in paths:
                if not os.path.isfile(filename) or not os.access(filename, os.R_OK):
                    continue
                # Relative paths retain their historical current-directory basis.
                with io.open(filename, encoding=getattr(self.fp, 'encoding', None)) as stream:
                    child = MySQLConfigParserFilter(stream, self._active_paths)
                    for included_line in child:
                        yield included_line
