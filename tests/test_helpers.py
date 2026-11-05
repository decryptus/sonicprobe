import base64
import os
import shutil
import tempfile
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


class TemporaryWriteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = os.path.join(self.directory, 'certificate')

    def test_replacement_is_staged_beside_target_and_keeps_metadata(self):
        with open(self.path, 'wb') as target:
            target.write(b'old')
        os.chmod(self.path, 0o640)
        before = os.stat(self.path)

        def chunks():
            self.assertEqual(len(os.listdir(self.directory)), 2)
            yield b'new'
            with open(self.path, 'rb') as target:
                self.assertEqual(target.read(), b'old')
            yield b' contents'

        self.assertEqual(helpers.file_w_tmp(chunks(), self.path, 'wb'), self.path)
        self.assertEqual(os.listdir(self.directory), ['certificate'])
        with open(self.path, 'rb') as target:
            self.assertEqual(target.read(), b'new contents')
        after = os.stat(self.path)
        self.assertNotEqual(before.st_ino, after.st_ino)
        self.assertEqual((before.st_mode, before.st_uid, before.st_gid),
                         (after.st_mode, after.st_uid, after.st_gid))

    def test_partial_write_is_cleaned_up_and_target_survives(self):
        def interrupted():
            yield 'partial'
            raise ValueError('source failed')

        helpers.file_w_tmp(['original'], self.path)
        with self.assertRaises(ValueError):
            helpers.file_w_tmp(interrupted(), self.path)
        with open(self.path) as target:
            self.assertEqual(target.read(), 'original')
        self.assertEqual(os.listdir(self.directory), ['certificate'])

    def test_directory_and_anonymous_tempfile_return_contracts(self):
        self.assertEqual(helpers.file_w_tmp(['in dir'], self.directory), self.directory)
        name, = os.listdir(self.directory)
        with open(os.path.join(self.directory, name)) as generated:
            self.assertEqual(generated.read(), 'in dir')
        path = helpers.file_w_tmp(['standalone'])
        self.addCleanup(os.unlink, path)
        with open(path) as generated:
            self.assertEqual(generated.read(), 'standalone')
