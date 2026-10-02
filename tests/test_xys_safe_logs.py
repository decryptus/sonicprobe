"""Rejected documents must not be interpolated in built-in validation logs."""
import logging
from contextlib import contextmanager
import unittest
from sonicprobe.libs import xys


_COLLECTION_SCHEMA = 'values: !~~seqlen(1,1) [ !!str ]'
_MAPPING_SCHEMA = 'known: !!str'


@contextmanager
def captured_errors():
    """Capture actual formatted records, including on Python 2.7."""
    records = []
    class CaptureHandler(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())
    handler = CaptureHandler(logging.ERROR)
    xys.LOG.addHandler(handler)
    try:
        yield records
    finally:
        xys.LOG.removeHandler(handler)
        handler.close()


class SafeValidationLogsTests(unittest.TestCase):
    def test_rejected_collection_does_not_disclose_its_values(self):
        schema = xys.load(_COLLECTION_SCHEMA)
        with captured_errors() as logged:
            self.assertFalse(xys.validate({'values': ['PRIVATE_VALUE', 'other']}, schema))
        self.assertTrue(logged)
        self.assertNotIn('PRIVATE_VALUE', '\n'.join(logged))
        self.assertTrue(xys.validate({'values': ['accepted']}, schema))

    def test_forbidden_document_key_is_not_logged(self):
        schema = xys.load(_MAPPING_SCHEMA)
        with captured_errors() as logged:
            self.assertFalse(xys.validate({'known': 'ok', 'PRIVATE_KEY': 'PRIVATE_VALUE'}, schema))
        self.assertTrue(logged)
        self.assertNotIn('PRIVATE_', '\n'.join(logged))

    def test_dynamic_length_key_is_not_logged(self):
        for value, minimum, maximum in ((1, 1, 2), ('', 1, 2), ('long', 1, 2)):
            with captured_errors() as logged:
                self.assertFalse(xys._valid_len('PRIVATE_KEY', value, minimum, maximum))
            self.assertTrue(logged)
            self.assertNotIn('PRIVATE_KEY', '\n'.join(logged))
