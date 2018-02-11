# -*- coding: utf-8 -*-

from datetime import datetime

class SPValidatorDate(object):
    def __init__(self, xformat = None):
        self.xformat    = xformat

    def validate(self, value, xformat = None):
        if not xformat:
            if self.xformat:
                xformat = self.xformat
            else:
                xformat = "%Y-%m-%d"

        try:
            datetime.strptime(value, xformat)
            return True
        except ValueError:
            return False

class SPValidatorDateTime(object):
    def __init__(self, xformat = None):
        self.xformat    = xformat

    def validate(self, value, xformat = None):
        if not xformat:
            if self.xformat:
                xformat = self.xformat
            else:
                xformat = "%Y-%m-%d %H:%M:%S"

        try:
            datetime.strptime(value, xformat)
            return True
        except ValueError:
            return False
