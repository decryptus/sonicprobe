# -*- coding: utf-8 -*-

import re

EMAIL_VALIDATOR = re.compile(r'^[a-z0-9-]+(\.[a-z0-9-]+)*(\.[a-z]{2,4})$').match

class SPValidatorEmail:
    def __init__(self):
        pass

    @staticmethod
    def valid_email_local(local_part):
        atom       = '\!#\$%&\'\*\+\-\/0-9\=\?A-Z\^_`a-z\{\|\}~'
        qtext      = '\x20\x21\x23-\x5B\x5D-\x7E'
        quotedpair = '\(\)\<\>\[\]\:;@\\\,\."'
        # if there is no local part stop and return false
        if len(local_part) < 1:
            return False

        reg_mail = re.compile('^(?:['+atom+']+(?:\.['+atom+']+)*|'+
                              '"(?:['+qtext+']|'+
                              '\\\['+quotedpair+'])+")$')

        if not isinstance(local_part, basestring) \
           or len(local_part) > 64 \
           or not reg_mail.match(local_part):
            return False

        return True

    @staticmethod
    def valid_email_address(address):
        return isinstance(address, basestring) and \
               EMAIL_VALIDATOR(address)

    @staticmethod
    def validate(email):
        if isinstance(email, basestring) is False \
           or len(email) > 320 \
           or email.find('@') == -1:
            return False

        pos        = email.find('@')
        local_part = email[0:pos]
        address    = email[pos + 1:]

        return SPValidatorEmail.valid_email_local(local_part) \
               and SPValidatorEmail.valid_email_address(address)
