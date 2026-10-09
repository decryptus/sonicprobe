"""Generate short-lived synthetic certificates for disposable CI containers."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

root = Path(sys.argv[1])
root.mkdir(mode=0o700, parents=True, exist_ok=True)
now = datetime.now(timezone.utc)


def issue(name, *, issuer=None, ca=False, expired=False, client=False):
    key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'tls_client' if client else name)])
    builder = (x509.CertificateBuilder().subject_name(subject)
               .issuer_name(issuer[0].subject if issuer else subject).public_key(key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(now-timedelta(days=3))
               .not_valid_after(now+timedelta(days=-1 if expired else 3))
               .add_extension(x509.BasicConstraints(ca=ca,path_length=None),critical=True)
               .add_extension(x509.KeyUsage(digital_signature=True,key_encipherment=not ca,
                    content_commitment=False,data_encipherment=False,key_agreement=False,
                    key_cert_sign=ca,crl_sign=ca,encipher_only=None,decipher_only=None),critical=True))
    if not ca:
        builder=builder.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH if client else ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
        if not client: builder=builder.add_extension(x509.SubjectAlternativeName([x509.DNSName('sql-tls.test')]),critical=False)
    cert=builder.sign(issuer[1] if issuer else key,hashes.SHA256())
    (root/(name+'.pem')).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private=root/(name+'.key')
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    private.chmod(0o600)
    return cert,key

ca=issue('ca',ca=True)
issue('wrong-ca',ca=True)
issue('server',issuer=ca)
issue('expired',issuer=ca,expired=True)
issue('client',issuer=ca,client=True)
