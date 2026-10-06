import os
import shutil
import stat
import tempfile
import unittest
from OpenSSL import crypto
from sonicprobe.libs.gencert import GenCert, CriticalExt

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
        self.assertTrue(csr.is_signature_valid if hasattr(csr, 'is_signature_valid') else csr.verify(key))
        for path in (key_path, csr_path, cert_path):
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            with open(path, 'rb') as stream:
                self.assertTrue(stream.read().startswith(b'-----BEGIN'))

    def test_explicit_legacy_digest_selection_is_preserved(self):
        self.assertEqual(GenCert(digest_type='sha1').digest_type, 'sha1')

    def test_csr_extensions_survive_without_removed_openssl_api(self):
        from cryptography import x509
        generator = GenCert()
        key = generator.make_privatekey()
        csr = generator.make_certreq(key, {'CN': 'example.test'},
            basicConstraints=CriticalExt(['CA:FALSE']),
            keyUsage=CriticalExt(['digitalSignature', 'keyEncipherment']),
            extendedKeyUsage=['serverAuth', 'clientAuth'],
            subjectAltName=['DNS:example.test', 'IP:127.0.0.1', 'URI:https://example.test/', 'email:admin@example.test'],
            nsCertType=['server'])
        self.assertTrue(csr.is_signature_valid if hasattr(csr, 'is_signature_valid') else csr.verify(key))
        parsed = csr if hasattr(csr, 'public_bytes') else csr.to_cryptography()
        self.assertEqual(len(parsed.extensions), 5)
        self.assertTrue(parsed.extensions.get_extension_for_class(x509.BasicConstraints).critical)
        self.assertFalse(parsed.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        self.assertEqual(parsed.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName), ['example.test'])

    def test_certificate_does_not_copy_unapproved_csr_extensions(self):
        from cryptography import x509
        generator = GenCert()
        key = generator.make_privatekey()
        csr = generator.make_certreq(key, {'CN': 'example.test'}, basicConstraints=CriticalExt(['CA:TRUE']))
        ca = crypto.X509()
        ca.get_subject().CN = 'Test CA'
        certificate = generator.make_certificate(csr, ca, key, 43)
        parsed = x509.load_pem_x509_certificate(crypto.dump_certificate(crypto.FILETYPE_PEM, certificate))
        self.assertEqual(len(parsed.extensions), 0)

    def test_invalid_extension_is_rejected(self):
        generator = GenCert()
        with self.assertRaises((ValueError, crypto.Error)):
            generator.make_certreq(generator.make_privatekey(), {'CN': 'example.test'}, keyUsage=['notAUsage'])

    @unittest.skipIf(hasattr(crypto, 'X509Extension'), 'modern extension bridge only')
    def test_modern_subject_and_authority_key_identifiers(self):
        import datetime
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.x509.oid import NameOID
        generator = GenCert()
        key = generator.make_privatekey()
        private = key.to_cryptography_key()
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u'Test CA')])
        now = datetime.datetime.now(datetime.timezone.utc)
        ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
              .public_key(private.public_key()).serial_number(42)
              .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
              .add_extension(x509.SubjectKeyIdentifier.from_public_key(private.public_key()), False)
              .sign(private, hashes.SHA256()))
        issuer = crypto.X509.from_cryptography(ca)
        csr = generator.make_certreq(key, {'CN': 'example.test'},
            subject=issuer, subjectKeyIdentifier=['hash'], issuer=issuer,
            authorityKeyIdentifier=['keyid:always', 'issuer:always'])
        extensions = csr.extensions if hasattr(csr, 'extensions') else csr.to_cryptography().extensions
        ski = extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value
        aki = extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value
        self.assertEqual(aki.key_identifier, ski.digest)
        self.assertEqual(aki.authority_cert_serial_number, 42)

    @unittest.skipIf(hasattr(crypto, 'X509Extension'), 'modern CSR API only')
    def test_modern_csr_type_subject_aliases_and_export(self):
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding
        from cryptography.x509.oid import NameOID
        generator = GenCert()
        key = generator.make_privatekey()
        csr = generator.make_certreq(key, {'commonName': u'example.test',
            'O': u'Example', 'C': 'FR', 'emailAddress': 'admin@example.test',
            '2.5.4.11': 'Operations', 'L': None})
        self.assertIsInstance(csr, x509.CertificateSigningRequest)
        self.assertTrue(csr.is_signature_valid)
        loaded = x509.load_pem_x509_csr(csr.public_bytes(Encoding.PEM))
        self.assertEqual(loaded.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value, 'example.test')
        ca = crypto.X509()
        ca.get_subject().CN = 'CA'
        cert = generator.make_certificate(loaded, ca, key, 44)
        parsed = cert.to_cryptography()
        self.assertEqual(parsed.subject, loaded.subject)
        self.assertEqual(parsed.public_key().public_numbers(), loaded.public_key().public_numbers())

    @unittest.skipIf(hasattr(crypto, 'X509Extension'), 'modern CSR API only')
    def test_invalid_csr_signature_is_rejected(self):
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding
        generator = GenCert()
        key = generator.make_privatekey()
        csr = generator.make_certreq(key, {'CN': 'example.test'})
        encoded = bytearray(csr.public_bytes(Encoding.DER))
        encoded[-1] ^= 1
        invalid = x509.load_der_x509_csr(bytes(encoded))
        with self.assertRaises(ValueError):
            generator.make_certificate(invalid, crypto.X509(), key, 45)
