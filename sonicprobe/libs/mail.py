# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Origin headers for outgoing email, independent of SMTP submission."""

from email.utils import formatdate, make_msgid, parseaddr
from uuid import uuid4


def ensure_message_headers(message):
    """Fill missing Date and Message-ID headers in place on an email Message."""
    if "Date" not in message:
        message["Date"] = formatdate(usegmt=True)
    if "Message-ID" not in message:
        # The network validator itself uses sonicprobe.helpers, a caller of this module.
        from sonicprobe.libs.network import valid_domain

        address = parseaddr(message.get("From", ""))[1]
        local, separator, domain = address.rpartition("@")
        if local and separator and valid_domain(domain):
            message["Message-ID"] = "<%s@%s>" % (uuid4().hex, domain)
        else:
            message["Message-ID"] = make_msgid()
