import base64
import unittest
from six import BytesIO
from sonicprobe import helpers

class HelperTests(unittest.TestCase):
    def test_file_reads_and_base64_roundtrip(self):
        data = b'hello\x00\xff' * 1000
        self.assertEqual(helpers.read_large_file(BytesIO(data), buffer_size=13), data)
        encoded = helpers.base64_encode_file(BytesIO(data), chunk_size=13)
        self.assertEqual(encoded.encode('ascii'), base64.b64encode(data))
        wrapped = b'\r\n'.join(encoded.encode('ascii')[i:i+7] for i in range(0, len(encoded), 7))
        self.assertEqual(helpers.base64_decode_file(BytesIO(wrapped), chunk_size=11), data)

    def test_small_chunks_fail_instead_of_silently_truncating(self):
        for function, size in ((helpers.base64_encode_file, 2), (helpers.base64_decode_file, 3)):
            with self.assertRaises(ValueError):
                function(BytesIO(b'hello'), chunk_size=size)
        with self.assertRaises(ValueError):
            helpers.read_large_file(BytesIO(b'hello'), buffer_size=0)

    def test_yaml_rejects_python_constructors(self):
        with self.assertRaises(Exception):
            helpers.load_yaml('!!python/object/apply:os.system [echo test]')
