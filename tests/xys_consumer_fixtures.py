# -*- coding: utf-8 -*-
# Schema excerpts: Copyright 2018-2022 fjord-technologies and contributing authors.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Frozen public consumer schemas; provenance is (repo, path, Git blob SHA).

These contract fixtures are not full application integration tests.
"""

SCHEMAS = [('decryptus/nsaproxy',
  'nsaproxy/modules/pdns.py',
  '0207dcc32260825cb4d4977289f7b692887be94c',
  'ENDPOINT_GET_QSCHEMA',
  '\n'
  '    server_id: !!str\n'
  '    endpoint:  !!str\n'
  '    id*:       !!str\n'
  '    command*:  !~~enum(check,export)\n'
  '    '),
 ('decryptus/nsaproxy',
  'nsaproxy/modules/pdns.py',
  '0207dcc32260825cb4d4977289f7b692887be94c',
  'ENDPOINT_PUT_QSCHEMA',
  '\n'
  '    server_id: !!str\n'
  '    endpoint:  !!str\n'
  '    id:        !!str\n'
  '    command*:  !~~enum(axfr-retrieve,notify,rectify)\n'
  '    domain*:   !!str\n'
  '    '),
 ('decryptus/nsaproxy',
  'nsaproxy/modules/pdns.py',
  '0207dcc32260825cb4d4977289f7b692887be94c',
  'ENDPOINT_POST_QSCHEMA',
  '\n    server_id: !!str\n    endpoint:  !~~enum(zones)\n    '),
 ('decryptus/nsaproxy',
  'nsaproxy/modules/pdns.py',
  '0207dcc32260825cb4d4977289f7b692887be94c',
  'ENDPOINT_POST_PSCHEMA',
  '\n'
  '    nameservers?:  [ !~~callback(pdns.domain) ]\n'
  '    masters?:      [ !~~callback(pdns.ipaddr) ]\n'
  '    kind:          !~~ienum(native,master,primary,slave,secondary)\n'
  '    name:          !~~callback(pdns.domain)\n'
  '    account?:      !!str\n'
  '    soa_edit_api?: !~~enum(DEFAULT,INCREASE,INCEPTION-INCREMENT,EPOCH,INCEPTION-EPOCH)\n'
  '    '),
 ('decryptus/nsaproxy',
  'nsaproxy/modules/pdns.py',
  '0207dcc32260825cb4d4977289f7b692887be94c',
  'ENDPOINT_PATCH_QSCHEMA',
  '\n    server_id: !!str\n    endpoint:  !~~enum(zones)\n    id:        !!str\n    '),
 ('decryptus/nsaproxy',
  'nsaproxy/modules/pdns.py',
  '0207dcc32260825cb4d4977289f7b692887be94c',
  'ENDPOINT_PATCH_PSCHEMA',
  '\n'
  '    nameservers?:  [ !~~callback(pdns.domain) ]\n'
  '    masters?:      [ !~~callback(pdns.ipaddr) ]\n'
  '    kind?:         !~~ienum(native,primary,secondary,master,slave)\n'
  '    name?:         !~~callback(pdns.domain)\n'
  '    soa_edit_api?: !~~enum(INCEPTION-INCREMENT,EPOCH,INCEPTION-EPOCH)\n'
  '    rrsets?:       !~~seqlen(0,9999)\n'
  '      - comments?:\n'
  '          - content:  !!str\n'
  '          - account:  !!str\n'
  '      - records:\n'
  '          - content*: !!str\n'
  '            disabled: !~~isBool\n'
  '            set-prt?: !~~isBool\n'
  '        changetype:   !~~enum(DELETE,REPLACE)\n'
  '        type:    !~~enum(A,AAAA,ALIAS,CAA,CNAME,RCNAME,MX,NS,PTR,SOA,SPF,SRV,TXT)\n'
  '        name:    !!str\n'
  '        ttl?:    !~~uint\n'
  '    '),
 ('decryptus/nsaproxy',
  'nsaproxy/modules/pdns.py',
  '0207dcc32260825cb4d4977289f7b692887be94c',
  'ENDPOINT_DELETE_QSCHEMA',
  '\n    server_id: !!str\n    endpoint:  !~~enum(zones)\n    id:        !!str\n    '),
 ('decryptus/nsaproxy',
  'nsaproxy/modules/pdns.py',
  '0207dcc32260825cb4d4977289f7b692887be94c',
  'ENDPOINT_VALIDATE_QSCHEMA',
  '\n    server_id: !!str\n    endpoint:  !!str\n    id:        !~~callback(pdns.domain)\n    '),
 ('decryptus/covenant',
  'covenant/modules/probes.py',
  'f58f0573e27a75d42bd4af8e70cd4024e1f8ca09',
  'PROBES_QSCHEMA',
  '\n    endpoint: !!str\n    target*: !!str\n    '),
 ('decryptus/auton',
  'auton/classes/job_schema.py',
  '63d0ec5166113918732012b63db351c50d98fa04',
  'RUN_QSCHEMA',
  '\nendpoint: !!str\nid: !!str\n'),
 ('decryptus/auton',
  'auton/classes/job_schema.py',
  '63d0ec5166113918732012b63db351c50d98fa04',
  'RUN_PSCHEMA',
  '\n'
  'env*:\n'
  '  !~~regex? (0,64) job.envname: !!str\n'
  'envfiles*: !~~seqlen(0,64) [ !!str ]\n'
  'args*: !~~seqlen(0,64) [ !!str ]\n'
  'argfiles*: !~~seqlen(0,64)\n'
  '  - arg: !!str\n'
  '    content: !!str\n'
  '    filename: !!str\n'),
 ('decryptus/covenant',
  'covenant/modules/metrics.py',
  'f773d81d1710526c4ba623fb3ce0b5e2eba2c6b3',
  'METRICS_QSCHEMA',
  '\n    endpoint: !!str\n    target*: !!str\n    '),
 ('decryptus/certlord',
  'certlord/modules/ssl_certs.py',
  'b0f41f71443e455b8e4941b4677bae801d0c17fa',
  'SAVE_PSCHEMA',
  '\n'
  '    domain: !~~callback(ssl_certs.sub_domain)\n'
  '    cert![1000,5000]: !!str\n'
  '    chain*[0,6000]: !!str\n'
  '    key![1000,5000]: !!str\n'
  '    '),
 ('decryptus/certlord',
  'certlord/modules/ssl_certs.py',
  'b0f41f71443e455b8e4941b4677bae801d0c17fa',
  'VALIDATE_QSCHEMA',
  '\n    sub_domain: !~~callback(ssl_certs.sub_domain)\n    '),
 ('decryptus/certlord',
  'certlord/modules/ssl_certs.py',
  'b0f41f71443e455b8e4941b4677bae801d0c17fa',
  'UPSERT_QSCHEMA',
  '\n    certificate_id: !~~callback(ssl_certs.certificate_id)\n    '),
 ('decryptus/certlord',
  'certlord/modules/ssl_certs.py',
  'b0f41f71443e455b8e4941b4677bae801d0c17fa',
  'UPSERT_PSCHEMA',
  '\n    domains: !~~seqlen(1,1) [ !~~callback(ssl_certs.sub_domain) ]\n    '),
 ('decryptus/certlord',
  'certlord/modules/ssl_certs.py',
  'b0f41f71443e455b8e4941b4677bae801d0c17fa',
  'INDEX_QSCHEMA',
  '\n    certificate_id: !~~callback(ssl_certs.certificate_id)\n    '),
 ('decryptus/certlord',
  'certlord/modules/letsencrypt.py',
  '031ae50b0dd7107f5115a79630681c63d0c37f7e',
  'WELL_KNOWN_DELETE_QSCHEMA',
  '\n    challenge: !~~regex(letsencrypt.challenge)\n    '),
 ('decryptus/certlord',
  'certlord/modules/letsencrypt.py',
  '031ae50b0dd7107f5115a79630681c63d0c37f7e',
  'WELL_KNOWN_GET_QSCHEMA',
  '\n    challenge: !~~regex(letsencrypt.challenge)\n    '),
 ('decryptus/certlord',
  'certlord/modules/letsencrypt.py',
  '031ae50b0dd7107f5115a79630681c63d0c37f7e',
  'WELL_KNOWN_PUT_QSCHEMA',
  '\n    challenge: !~~regex(letsencrypt.challenge)\n    ')]
