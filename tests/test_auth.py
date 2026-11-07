# -*- python -*-
#
# Copyright (C) 2001-2007 Jason R. Mastaler <jason@mastaler.com>
#
# This file is part of TMDA.
#
# TMDA is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.  A copy of this license should
# be included in the file COPYING.

"""Regression tests for Python 3 authentication compatibility helpers."""

import base64
import hashlib
import hmac
import os
import tempfile
import unittest
import types
from unittest.mock import patch

from TMDA.Auth import Auth


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        # Test only standalone helper methods without initializing the daemon.
        self.auth = object.__new__(Auth)

    def test_base64_round_trip(self):
        value = 'user:pass'
        encoded = self.auth._Auth__b64_encode(value)
        self.assertEqual(encoded, base64.b64encode(value.encode('ascii')).decode('ascii'))
        self.assertEqual(self.auth._Auth__b64_decode(encoded), value)

    def test_file_authentication_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'tmdauth')
            with open(path, 'w', encoding='ascii') as fp:
                fp.write('Alice@Example.com:secret\n')
            self.assertEqual(
                self.auth._Auth__authfile2dict(path),
                {'alice@example.com': 'secret'},
            )

    def test_legacycrypt_password_verification(self):
        auth = self.auth
        auth.debug = lambda message: None
        auth._Auth__authfile = '/tmp/tmdauth-test'
        auth._Auth__authdict = {'alice': '$6$known$hash'}
        auth._Auth__authfile_allows_cleartext = False
        auth._Auth__update_authdict = lambda: None
        backend = types.ModuleType('legacycrypt')
        backend.crypt = lambda password, salt: '$6$known$hash' if (
            password == 'correct' and salt == '$6'
        ) else '*'
        with patch.dict('sys.modules', {'crypt': None, 'legacycrypt': backend}):
            self.assertTrue(auth.authenticate_plain_file('alice', 'correct'))
            self.assertFalse(auth.authenticate_plain_file('alice', 'incorrect'))

    def test_cram_md5_legacy_digest(self):
        self.auth.supports_cram_md5 = lambda: True
        self.auth._Auth__update_authdict = lambda: None
        self.auth._Auth__authdict = {'alice': 'secret'}
        ticket = '<1234@example.com>'
        digest = hmac.new(b'secret', ticket.encode('ascii'), hashlib.md5).hexdigest()
        response = base64.b64encode(('alice ' + digest).encode('ascii')).decode('ascii')
        self.assertTrue(self.auth.authenticate_cram_md5(response, ticket))


if __name__ == '__main__':
    unittest.main()
