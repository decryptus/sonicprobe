import os
import shutil
import stat
import tempfile
import unittest
from OpenSSL import crypto
from sonicprobe.libs.gencert import GenCert

class CertificateTests(unittest.TestCase):
    def test_pem_exports_and_sha256_default(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        generator = GenCert()
        key_path, csr_path, cert_path = [os.path.join(root, name) for name in ('key.pem', 'csr.pem', 'cert.pem')]
        key = generator.make_privatekey(key_path)
        csr = generator.make_certreq(key, {'CN': 'example.test'}, csr_path)
        ca = crypto.X509()
        ca.get_subject().CN = 'Test CA'
        cert = generator.make_certificate(csr, ca, key, 42, cert_path)
        self.assertEqual(cert.get_signature_algorithm(), b'sha256WithRSAEncryption')
        self.assertEqual(cert.get_version(), 2)
        self.assertEqual(cert.get_serial_number(), 42)
        self.assertTrue(csr.verify(key))
        for path in (key_path, csr_path, cert_path):
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            with open(path, 'rb') as stream:
                self.assertTrue(stream.read().startswith(b'-----BEGIN'))

    def test_explicit_legacy_digest_selection_is_preserved(self):
        self.assertEqual(GenCert(digest_type='sha1').digest_type, 'sha1')
