import unittest
from email import message_from_string
from email.message import Message
from email.utils import parsedate_tz

try:
    from unittest import mock
except ImportError:
    import mock

from sonicprobe import helpers
from sonicprobe.libs.mail import ensure_message_headers


class OriginHeaderTests(unittest.TestCase):
    def test_add_only_missing_headers_and_keep_retry_identity(self):
        fresh = Message()
        fresh["From"] = "Service <contact@example.test>"
        ensure_message_headers(fresh)
        date, message_id = fresh["Date"], fresh["Message-ID"]
        self.assertEqual(parsedate_tz(date)[-1], 0)
        self.assertTrue(message_id.endswith("@example.test>"))
        ensure_message_headers(fresh)
        self.assertEqual(fresh.get_all("Date"), [date])
        self.assertEqual(fresh.get_all("Message-ID"), [message_id])

        partial = Message()
        partial["Message-ID"] = "<document-42@example.test>"
        ensure_message_headers(partial)
        self.assertEqual(partial.get_all("Message-ID"), ["<document-42@example.test>"])
        self.assertIsNotNone(parsedate_tz(partial["Date"]))

    def test_local_sender_and_existing_date(self):
        local = Message()
        local["From"] = "postmaster"
        local["Date"] = "Thu, 01 Jan 1970 00:00:00 +0000"
        ensure_message_headers(local)
        self.assertEqual(local.get_all("Date"), ["Thu, 01 Jan 1970 00:00:00 +0000"])
        self.assertTrue(local["Message-ID"].startswith("<"))
        self.assertTrue(local["Message-ID"].endswith(">"))
        self.assertIn("@", local["Message-ID"])

    def test_send_email_sets_headers_and_preserves_blind_envelope(self):
        with mock.patch("sonicprobe.helpers.smtplib.SMTP") as smtp:
            helpers.send_email(("Service", "sender@example.test"), "to@example.test",
                               "Subject", "Body", bcc="blind@example.test")
        sender, recipients, wire = smtp.return_value.sendmail.call_args[0]
        message = message_from_string(wire)
        self.assertEqual(sender, "sender@example.test")
        self.assertEqual(recipients, ["to@example.test", "blind@example.test"])
        self.assertIsNone(message["Bcc"])
        self.assertTrue(message["Message-ID"].endswith("@example.test>"))
        self.assertIsNotNone(parsedate_tz(message["Date"]))
