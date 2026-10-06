# GenCert migration and dependency compatibility

On Python 3.10 and newer, Sonicprobe now requires pyOpenSSL 26.4 or newer
(within 26.x), cryptography 50.x, and setuptools 83 or newer.

`GenCert.make_certreq()` returns a `cryptography.x509.CertificateSigningRequest`
on this dependency combination. The removed pyOpenSSL CSR API is no longer used.
Private keys and issued certificates retain their existing pyOpenSSL return types.
`make_certificate()` accepts the modern CSR and rejects an invalid CSR signature;
it does not automatically copy requested extensions into the issued certificate.
The issuing application remains responsible for extension authorization.

```python
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from sonicprobe.libs.gencert import GenCert

generator = GenCert()
key = generator.make_privatekey()
csr = generator.make_certreq(key, {'CN': 'example.test'},
                             subjectAltName=['DNS:example.test'])
assert csr.is_signature_valid
pem = csr.public_bytes(Encoding.PEM)
loaded = x509.load_pem_x509_csr(pem)
subject = loaded.subject
public_key = loaded.public_key()
```

Replace `csr.verify(key)` with `csr.is_signature_valid` to check the embedded
signature. If an expected key must also be matched, compare its public key with
`csr.public_key()` explicitly. Replace `get_subject()` and `get_pubkey()` with
`subject` and `public_key()`. Use `public_bytes(Encoding.PEM)` instead of
`crypto.dump_certificate_request()`, and `x509.load_pem_x509_csr()` instead of
`crypto.load_certificate_request()`.

Existing `export_file` PEM output and file permissions remain unchanged.
Common subject aliases (CN, C, ST, L, O, OU, emailAddress, serialNumber, SN,
givenName, title, DC, UID, street and postalCode), their mapped long names, and
dotted OIDs are accepted. Unsupported names are rejected. Extension options retain
critical flags, SANs, key usages, basic constraints and Netscape certificate type.
For modern subject key identifiers use `hash`; authority key identifiers accept
`keyid`, `keyid:always`, `issuer` and `issuer:always`. SHA-256 remains the default;
cryptography rejects obsolete signing algorithms even if the legacy configuration
setter accepts their names.

Python older than 3.10 retains the legacy dependency path and pyOpenSSL CSR
return type. This preserves the declared interpreter matrix; it does **not**
provide the modern dependency security fixes. Upgrade to Python 3.10 or newer
for the corrected dependency set. The legacy interpreter matrix must still run
in CI before a release. Some retained pyOpenSSL key/certificate methods are
deprecated upstream and need a later public-API migration.
