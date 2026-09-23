import logging
import threading
import unittest
try:
    from unittest import mock
except ImportError:
    import mock
from sonicprobe.sp_logging.QueueSMTPHandler import QueueSMTPHandler


class QueueLoggingTests(unittest.TestCase):
    def record(self, message):
        return logging.LogRecord('test', logging.ERROR, __file__, 1, message, (), None)

    def test_purge_respects_handler_lock_and_keeps_records_received_during_delivery(self):
        handler = QueueSMTPHandler('localhost', 'from@example.test', ['to@example.test'], 'test')
        self.addCleanup(handler.close)
        handler.emit(self.record('first'))
        sending, release, finished = threading.Event(), threading.Event(), threading.Event()
        def send(*args):
            sending.set()
            release.wait(3)
        def purge():
            handler.purge()
            finished.set()
        with mock.patch('sonicprobe.sp_logging.QueueSMTPHandler.smtplib.SMTP') as smtp:
            smtp.return_value.sendmail.side_effect = send
            handler.acquire()
            thread = threading.Thread(target=purge)
            thread.daemon = True
            thread.start()
            try:
                self.assertFalse(sending.wait(0.05))
            finally:
                handler.release()
            try:
                self.assertTrue(sending.wait(2))
                handler.emit(self.record('second'))
            finally:
                release.set()
                thread.join(3)
            self.assertTrue(finished.is_set())
            self.assertFalse(handler.isEmpty())
            handler.purge()
            messages = [call[0][2] for call in smtp.return_value.sendmail.call_args_list]
            self.assertEqual(len(messages), 2)
            self.assertIn('first', messages[0])
            self.assertNotIn('second', messages[0])
            self.assertIn('second', messages[1])
            self.assertTrue(handler.isEmpty())

    def test_quit_error_closes_transport_without_aborting_purge(self):
        handler = QueueSMTPHandler('localhost', 'from@example.test', ['to@example.test'], 'test')
        self.addCleanup(handler.close)
        handler.emit(self.record('message'))
        with mock.patch('sonicprobe.sp_logging.QueueSMTPHandler.smtplib.SMTP') as smtp:
            smtp.return_value.quit.side_effect = RuntimeError('transport already disconnected')
            handler.purge()
            smtp.return_value.close.assert_called_once_with()
