# -*- coding: utf-8 -*-
# Copyright (C) 2015-2019 Adrien Delle Cave
# SPDX-License-Identifier: GPL-3.0-or-later
"""sonicprobe.sp_logging.QueueSMTPHandler"""

import smtplib

from email.mime.text import MIMEText

from logging.handlers import SMTPHandler

from six import itervalues

from sonicprobe.libs.mail import ensure_message_headers


class QueueSMTPHandler(SMTPHandler):
    def __init__(self, mailhost, fromaddr, toaddrs, subject, logger_name = None):
        self.queue          = {}
        self.logger_name    = logger_name

        SMTPHandler.__init__(self, mailhost, fromaddr, toaddrs, subject)

    def isEmpty(self):
        self.acquire()
        try:
            return len(self.queue) == 0
        finally:
            self.release()

    def getSubject(self, record):
        if self.logger_name:
            return "[%s] %s Event" % (self.logger_name, record.levelname)
        return "%s Event" % record.levelname

    def emit(self, record):
        self.acquire()
        try:
            if record.levelname not in self.queue:
                self.queue[record.levelname] = []
            self.queue[record.levelname].append(record)
        finally:
            self.release()

    def purge(self):
        self.acquire()
        try:
            queue = self.queue
            self.queue = {}
        finally:
            self.release()

        for records in itervalues(queue):
            msg     = ""
            record  = None

            for record in records:
                msg += "%s\n" % self.format(record)

            if not record:
                continue

            smtp = None

            try:
                port = self.mailport
                if not port:
                    port = smtplib.SMTP_PORT
                smtp = smtplib.SMTP(self.mailhost, port)
                message = MIMEText(msg)
                message['From'] = self.fromaddr
                message['To'] = ','.join(self.toaddrs)
                message['Subject'] = self.getSubject(record)
                ensure_message_headers(message)
                smtp.sendmail(self.fromaddr, self.toaddrs, message.as_string())
            except Exception:
                self.handleError(record)
            finally:
                if smtp:
                    try:
                        smtp.quit()
                    except Exception:
                        smtp.close()
