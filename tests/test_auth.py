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
import pathlib
import sys
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


    def test_cleartext_authentication_without_crypt_on_python_313(self):
        auth = self.auth
        auth.debug = lambda message: None
        auth._Auth__authfile = '/tmp/tmdauth-cleartext-test'
        auth._Auth__authdict = {'alice': 'original-secret'}
        auth._Auth__authfile_allows_cleartext = True
        auth._Auth__update_authdict = lambda: None
        # Python >=3.13 has no standard crypt module. Preserve
        # file-based plaintext mode without an external dependency.
        with patch.dict('sys.modules', {'crypt': None, 'legacycrypt': None}):
            self.assertTrue(auth.authenticate_plain_file(
                'alice', 'original-secret'))
            self.assertFalse(auth.authenticate_plain_file(
                'alice', 'incorrect'))

    def test_encrypted_password_requires_crypt_backend_when_unavailable(self):
        auth = self.auth
        auth.debug = lambda message: None
        auth._Auth__authfile = '/tmp/tmdauth-encrypted-test'
        auth._Auth__authdict = {'alice': 'xxencrypted'}
        auth._Auth__authfile_allows_cleartext = False
        auth._Auth__update_authdict = lambda: None
        from TMDA import Errors
        with patch.dict('sys.modules', {'crypt': None, 'legacycrypt': None}):
            with self.assertRaises(Errors.AuthError):
                auth.authenticate_plain_file('alice', 'original-secret')


    def test_original_eight_bit_password_file_is_reversible(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'tmdauth')
            with open(path, 'wb') as stream:
                stream.write(b'alice:pass\xffword\n')
            self.assertEqual(
                self.auth._Auth__authfile2dict(path),
                {'alice': 'pass\xffword'})

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



    def test_virtual_user_home_lookup(self):
        self.auth._Auth__default_tmda_dir = '.tmda'
        self.auth.setup_vuser('/usr/local/bin/vhome')
        with patch('TMDA.Util.getvuserhomedir',
                   return_value='/home/virtual/alice') as lookup:
            self.assertEqual(
                self.auth.get_homedir('alice', 'example.org'),
                '/home/virtual/alice')
            self.assertEqual(
                self.auth.get_tmdadir('alice', 'example.org'),
                '/home/virtual/alice/.tmda')
            lookup.assert_called_with(
                'alice', 'example.org', '/usr/local/bin/vhome')

    def test_config_directory_user_lookup(self):
        self.auth._Auth__default_tmda_dir = '.tmda'
        self.auth.setup_configdir('/srv/tmda-users')
        self.assertEqual(
            self.auth.get_homedir('alice'),
            '/srv/tmda-users/alice')
        self.assertEqual(
            self.auth.get_tmdadir('alice'),
            '/srv/tmda-users/alice/.tmda')

    def test_checkpassword_command_does_not_duplicate_arguments(self):
        self.auth.debug = lambda message: None
        self.auth._Auth__ownerID = os.getuid()
        with patch('TMDA.Util.CanExec', return_value=True):
            self.auth.init_checkpw('/usr/local/bin/checkpassword /usr/bin/true')
        self.assertEqual(self.auth._Auth__authprog,
                         '/usr/local/bin/checkpassword /usr/bin/true')

    def test_checkpassword_fd3_binary_credentials(self):
        """The checkpassword child receives NUL bytes on fd 3."""
        with tempfile.TemporaryDirectory() as directory:
            script = pathlib.Path(directory) / 'read_fd3.py'
            script.write_text(
                'import os, sys\n'
                'data = os.read(3, 1024)\n'
                'sys.exit(0 if data == b"alice\\0secret\\0" else 4)\n',
                encoding='ascii')
            self.auth.debug = lambda message: None
            status = self.auth._Auth__pipefd3(
                sys.executable + ' ' + str(script),
                'alice\0secret\0')
            self.assertEqual(status, 0)

    def test_checkpassword_fd3_failure_status(self):
        with tempfile.TemporaryDirectory() as directory:
            script = pathlib.Path(directory) / 'reject.py'
            script.write_text('import sys\nsys.exit(7)\n', encoding='ascii')
            self.auth.debug = lambda message: None
            self.assertEqual(self.auth._Auth__pipefd3(
                sys.executable + ' ' + str(script), b'no-match\0'), 7)


    def test_original_remote_imap_and_imaps_login_paths(self):
        auth = self.auth
        auth.debug = lambda message: None
        auth._Auth__defaultauthports = {'imap': 143, 'imaps': 993}
        auth._Auth__localip = '127.0.0.1'

        class FakeIMAP:
            def __init__(self, host, port):
                self.host, self.port = host, port
            def login(self, user, password):
                return ('OK', [b'logged in']) if (
                    user == 'alice' and password == 'secret'
                ) else ('NO', [])
            def logout(self):
                return ('BYE', [])

        for protocol, port in (('imap', 143), ('imaps', 993)):
            with self.subTest(protocol=protocol):
                auth._Auth__authremote = {
                    'proto': protocol, 'host': '127.0.0.1', 'port': port}
                target = ('TMDA.Auth.imaplib.IMAP4_SSL' if protocol == 'imaps'
                          else 'TMDA.Auth.imaplib.IMAP4')
                with patch(target, FakeIMAP):
                    self.assertTrue(auth.authenticate_plain_remote(
                        'alice', 'secret'))
                    self.assertFalse(auth.authenticate_plain_remote(
                        'alice', 'wrong'))

    def test_original_remote_pop3_and_apop_login_paths(self):
        auth = self.auth
        auth.debug = lambda message: None
        auth._Auth__defaultauthports = {'pop3': 110, 'apop': 110}
        auth._Auth__localip = '127.0.0.1'

        class FakePOP3:
            def __init__(self, host, port):
                self.user_name = None
            def user(self, user):
                self.user_name = user
            def pass_(self, password):
                if password != 'secret':
                    raise ValueError('bad password')
            def apop(self, user, password):
                if password != 'secret':
                    raise ValueError('bad password')
            def quit(self):
                return b'+OK'

        for protocol in ('pop3', 'apop'):
            with self.subTest(protocol=protocol):
                auth._Auth__authremote = {
                    'proto': protocol, 'host': '127.0.0.1', 'port': 110}
                with patch('TMDA.Auth.poplib.POP3', FakePOP3):
                    self.assertTrue(auth.authenticate_plain_remote(
                        'alice', 'secret'))

    def test_original_remote_ldap_simple_bind_path(self):
        auth = self.auth
        auth.debug = lambda message: None
        auth._Auth__defaultauthports = {'ldap': 389}
        auth._Auth__localip = '127.0.0.1'
        auth._Auth__authremote = {
            'proto': 'ldap', 'host': '127.0.0.1', 'port': 389,
            'dn': 'uid=%(user)s,dc=example,dc=org'}

        bindings = []
        class FakeLDAPConnection:
            def simple_bind_s(self, dn, password):
                bindings.append((dn, password))
            def unbind_s(self):
                pass
        ldap = types.ModuleType('ldap')
        ldap.initialize = lambda address: FakeLDAPConnection()
        with patch.dict('sys.modules', {'ldap': ldap}):
            self.assertTrue(auth.authenticate_plain_remote('alice', 'secret'))
        self.assertEqual(bindings, [
            ('uid=alice,dc=example,dc=org', 'secret')])

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
