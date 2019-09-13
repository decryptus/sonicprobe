# -*- coding: utf-8 -*-
# Copyright 2008-2019 Proformatique
# SPDX-License-Identifier: GPL-3.0-or-later
"""sonicprobe.libs.mysql_config_parser"""

import os
import re

# pylint: disable=unused-import
from six.moves.configparser import ConfigParser, Error, NoSectionError, DuplicateSectionError, \
        NoOptionError, InterpolationError, InterpolationMissingOptionError, \
        InterpolationSyntaxError, InterpolationDepthError, ParsingError, \
        MissingSectionHeaderError, _default_dict
import six

class MySQLConfigParser(ConfigParser):
    if os.name == 'nt':
        RE_INCLUDE_FILE = re.compile(r'^[^\.]+(?:\.ini|\.cnf)$').match
    else:
        RE_INCLUDE_FILE = re.compile(r'^[^\.]+\.cnf$').match

    def __init__(self, defaults = None, dict_type = _default_dict, allow_no_value=True):
        ConfigParser.__init__(self, defaults, dict_type, allow_no_value)

    @staticmethod
    def valid_filename(filename):
        if isinstance(filename, six.string_types) and MySQLConfigParser.RE_INCLUDE_FILE(filename):
            return True

        return False

    def getboolean(self, section, option, retint=False): # pylint: disable=arguments-differ
        ret = ConfigParser.getboolean(self, section, option)

        if not retint:
            return ret

        return(int(ret))

    def read(self, filenames, encoding=None):
        if isinstance(filenames, six.string_types):
            filenames = [filenames]

        file_ok = []
        for filename in filenames:
            if self.valid_filename(os.path.basename(filename)):
                file_ok.append(filename)

        if six.PY2:
            return ConfigParser.read(self, file_ok)

        return ConfigParser.read(self, file_ok, encoding)

    def readfp(self, fp, filename=None):
        return ConfigParser.readfp(self, MySQLConfigParserFilter(fp), filename)

    def read_file(self, f, source=None):
        if six.PY2:
            return ConfigParser.readfp(self, MySQLConfigParserFilter(f), source)

        return ConfigParser.read_file(self, MySQLConfigParserFilter(f), source)


class MySQLConfigParserFilter(object): # pylint: disable=useless-object-inheritance
    RE_HEADER_OPT  = re.compile(r'^\s*\[[^\]]+\]\s*').match
    RE_INCLUDE_OPT = re.compile(r'^\s*!\s*(?:(include|includedir)\s+(.+))$').match

    def __init__(self, fp):
        self.fp     = fp
        self._lines = []

    def readline(self):
        if self._lines:
            line = self._lines.pop(0)
        else:
            line = self.fp.readline()

        sline = line.lstrip()

        if not sline or sline[0] != '!':
            if self.RE_HEADER_OPT(line):
                return line

            if sline.startswith('#'):
                return line

            if sline.startswith(';'):
                return line

            return line

        mline = self.RE_INCLUDE_OPT(sline)

        if not mline:
            raise ParsingError("Unable to parse the line: %r." % line)
            #return "#%s" % line

        opt = mline.group(2).strip()

        if not opt:
            raise ParsingError("Empty path for include or includir option (%r)." % line)
            #return "#%s" % line

        if mline.group(1) == 'include':
            if not MySQLConfigParser.RE_INCLUDE_FILE(opt):
                raise ParsingError("Wrong filename for include option (%r)." % line)
                #return "#%s" % line

            self._add_lines(opt)
        else:
            dirname = os.path.dirname(opt)
            for xfile in os.listdir(opt):
                if MySQLConfigParser.RE_INCLUDE_FILE(xfile):
                    self._add_lines(os.path.join(dirname, xfile))

        return self.readline()

    def _add_lines(self, xfile):
        if not os.path.isfile(xfile) or not os.access(xfile, os.R_OK):
            return

        xfilter = MySQLConfigParserFilter(open(xfile))
        lines = xfilter.fp.readlines()
        xfilter.fp.close()
        lines.extend(self._lines)
        self._lines = lines
