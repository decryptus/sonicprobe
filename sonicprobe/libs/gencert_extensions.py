# -*- coding: utf-8 -*-
"""Modern GenCert CSRs using cryptography; no removed pyOpenSSL CSR APIs."""
import ipaddress
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID, ObjectIdentifier
from sonicprobe.libs.gencert import CriticalExt, X509_TYPE_NAMES

_KEY_USAGES = ('digitalSignature', 'nonRepudiation', 'keyEncipherment',
              'dataEncipherment', 'keyAgreement', 'keyCertSign', 'cRLSign',
              'encipherOnly', 'decipherOnly')
_EXTENDED_USAGES = {'serverAuth': ExtendedKeyUsageOID.SERVER_AUTH,
                   'clientAuth': ExtendedKeyUsageOID.CLIENT_AUTH,
                   'codeSigning': ExtendedKeyUsageOID.CODE_SIGNING,
                   'emailProtection': ExtendedKeyUsageOID.EMAIL_PROTECTION,
                   'timeStamping': ExtendedKeyUsageOID.TIME_STAMPING,
                   'OCSPSigning': ExtendedKeyUsageOID.OCSP_SIGNING,
                   'anyExtendedKeyUsage': ObjectIdentifier('2.5.29.37.0')}
_NETSCAPE_BITS = {'client': 128, 'server': 64, 'email': 32, 'objsign': 16,
                  'sslCA': 4, 'emailCA': 2, 'objCA': 1}
_NETSCAPE_TYPE = ObjectIdentifier('2.16.840.1.113730.1.1')
_DIGESTS = {'sha224': hashes.SHA224, 'sha256': hashes.SHA256,
            'sha384': hashes.SHA384, 'sha512': hashes.SHA512,
            'sha1': hashes.SHA1, 'md5': hashes.MD5}


def _items(values):
    return [item.strip() for value in values for item in value.split(',')]


def _extension(name, values):
    items = _items(values)
    if name == 'basicConstraints':
        options = dict(item.split(':', 1) for item in items)
        if set(options) - set(['CA', 'pathlen']) or options.get('CA', 'FALSE') not in ('TRUE', 'FALSE'):
            raise ValueError('Invalid basicConstraints')
        return x509.BasicConstraints(options.get('CA', 'FALSE') == 'TRUE',
                                    int(options['pathlen']) if 'pathlen' in options else None)
    if name == 'keyUsage':
        if set(items) - set(_KEY_USAGES):
            raise ValueError('Unsupported keyUsage')
        return x509.KeyUsage(*[item in items for item in _KEY_USAGES])
    if name == 'extendedKeyUsage':
        return x509.ExtendedKeyUsage([_EXTENDED_USAGES[item] if item in _EXTENDED_USAGES
                                     else ObjectIdentifier(item) for item in items])
    if name == 'subjectAltName':
        names = []
        for item in items:
            kind, value = item.split(':', 1)
            if kind == 'DNS': names.append(x509.DNSName(value))
            elif kind == 'IP': names.append(x509.IPAddress(ipaddress.ip_address(value)))
            elif kind == 'URI': names.append(x509.UniformResourceIdentifier(value))
            elif kind == 'email': names.append(x509.RFC822Name(value))
            elif kind == 'RID': names.append(x509.RegisteredID(ObjectIdentifier(value)))
            else: raise ValueError('Unsupported subjectAltName type: %s' % kind)
        return x509.SubjectAlternativeName(names)
    if name == 'nsCertType':
        mask = 0
        for item in items:
            if item not in _NETSCAPE_BITS: raise ValueError('Unsupported nsCertType')
            mask |= _NETSCAPE_BITS[item]
        unused = 0
        if mask:
            while not mask & (1 << unused): unused += 1
        return x509.UnrecognizedExtension(_NETSCAPE_TYPE, bytes(bytearray([3, 2, unused, mask])))
    raise ValueError('Unsupported extension: %s' % name)


_NAME_OIDS = {
    'CN': NameOID.COMMON_NAME, 'commonName': NameOID.COMMON_NAME,
    'C': NameOID.COUNTRY_NAME, 'countryName': NameOID.COUNTRY_NAME,
    'ST': NameOID.STATE_OR_PROVINCE_NAME, 'stateOrProvinceName': NameOID.STATE_OR_PROVINCE_NAME,
    'L': NameOID.LOCALITY_NAME, 'localityName': NameOID.LOCALITY_NAME,
    'O': NameOID.ORGANIZATION_NAME, 'organizationName': NameOID.ORGANIZATION_NAME,
    'OU': NameOID.ORGANIZATIONAL_UNIT_NAME, 'organizationalUnitName': NameOID.ORGANIZATIONAL_UNIT_NAME,
    'emailAddress': NameOID.EMAIL_ADDRESS, 'serialNumber': NameOID.SERIAL_NUMBER,
    'SN': NameOID.SURNAME, 'surname': NameOID.SURNAME, 'givenName': NameOID.GIVEN_NAME,
    'title': NameOID.TITLE, 'DC': NameOID.DOMAIN_COMPONENT, 'domainComponent': NameOID.DOMAIN_COMPONENT,
    'UID': NameOID.USER_ID, 'userId': NameOID.USER_ID,
    'street': NameOID.STREET_ADDRESS, 'streetAddress': NameOID.STREET_ADDRESS,
    'postalCode': NameOID.POSTAL_CODE,
}


def make_certreq(pkey, attributes, digest, options):
    subject = []
    for name, value in attributes.items():
        if value is not None:
            oid = _NAME_OIDS[name] if name in _NAME_OIDS else ObjectIdentifier(name)
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            subject.append(x509.NameAttribute(oid, value))
    builder = x509.CertificateSigningRequestBuilder().subject_name(x509.Name(subject))
    for name in X509_TYPE_NAMES:
        if name in options:
            builder = builder.add_extension(_extension(name, options[name]), isinstance(options[name], CriticalExt))
    if options.get('subject') and 'subjectKeyIdentifier' in options:
        values = _items(options['subjectKeyIdentifier'])
        if values != ['hash']:
            raise ValueError('Modern subjectKeyIdentifier requires hash')
        extension = x509.SubjectKeyIdentifier.from_public_key(options['subject'].to_cryptography().public_key())
        builder = builder.add_extension(extension, isinstance(options['subjectKeyIdentifier'], CriticalExt))
    if options.get('issuer') and 'authorityKeyIdentifier' in options:
        values = _items(options['authorityKeyIdentifier'])
        if set(values) - set(['keyid', 'keyid:always', 'issuer', 'issuer:always']):
            raise ValueError('Unsupported authorityKeyIdentifier')
        issuer = options['issuer'].to_cryptography()
        keyid = None
        if 'keyid' in values or 'keyid:always' in values:
            try:
                keyid = issuer.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
            except x509.ExtensionNotFound:
                if 'keyid:always' in values: raise ValueError('Issuer has no subjectKeyIdentifier')
        include_issuer = 'issuer:always' in values or ('issuer' in values and keyid is None)
        extension = x509.AuthorityKeyIdentifier(keyid,
            [x509.DirectoryName(issuer.issuer)] if include_issuer else None,
            issuer.serial_number if include_issuer else None)
        builder = builder.add_extension(extension, isinstance(options['authorityKeyIdentifier'], CriticalExt))
    if digest not in _DIGESTS:
        raise ValueError('Unsupported modern CSR digest: %s' % digest)
    csr = builder.sign(pkey.to_cryptography_key(), _DIGESTS[digest]())
    return csr
