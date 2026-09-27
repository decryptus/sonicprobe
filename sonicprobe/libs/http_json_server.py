# -*- coding: utf-8 -*-
# Copyright 2007-2019 The Wazo Authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Legacy HTTPdis compatibility re-export.

This explicit import path is retained for existing consumers. New HTTP code
should import httpdis.ext.httpdis_json directly. Generic Sonicprobe utilities
must not import this shim; importing it deliberately requires HTTPdis.
"""

from httpdis.ext.httpdis_json import *

