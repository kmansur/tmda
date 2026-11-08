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

"""Exercise outgoing SMTP TLS negotiation without a network connection."""

import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class OutgoingSMTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import TMDA
        cls.old_defaults = getattr(TMDA, 'Defaults', None)
        cls.defaults = types.ModuleType('TMDA.Defaults')
        cls.defaults.SMTPHOST = 'localhost:2525'
        cls.defaults.SMTPSSL = True
        cls.defaults.SMTPSSL_KEYFILE = None
        cls.defaults.SMTPSSL_CERTFILE = None
        cls.defaults.SMTPAUTH_USERNAME = 'alice'
        cls.defaults.SMTPAUTH_PASSWORD = 'secret'
        cls.defaults.SMTP_MAX_SESSIONS_PER_CONNECTION = 0
        cls.modules = patch.dict(sys.modules, {'TMDA.Defaults': cls.defaults})
        cls.modules.start()
        TMDA.Defaults = cls.defaults
        sys.modules.pop('TMDA.SMTP', None)
        cls.module = importlib.import_module('TMDA.SMTP')

    @classmethod
    def tearDownClass(cls):
        import TMDA
        sys.modules.pop('TMDA.SMTP', None)
        if cls.old_defaults is None:
            delattr(TMDA, 'Defaults')
        else:
            TMDA.Defaults = cls.old_defaults
        cls.modules.stop()

    def test_starttls_context_login_and_delivery(self):
        smtp = MagicMock()
        context = MagicMock()
        with patch.object(self.module.smtplib, 'SMTP', return_value=smtp), \
                patch.object(self.module.ssl, 'create_default_context',
                             return_value=context):
            conn = self.module.Connection()
            conn.sendmail('alice@example.com', 'bob@example.com',
                          b'Subject: Test\r\n\r\nBody')
        smtp.connect.assert_called_once_with('localhost:2525')
        smtp.starttls.assert_called_once_with(context=context)
        smtp.ehlo.assert_called_once_with()
        smtp.login.assert_called_once_with('alice', 'secret')
        smtp.sendmail.assert_called_once_with(
            'alice@example.com', 'bob@example.com',
            b'Subject: Test\r\n\r\nBody')

    def test_incomplete_client_certificate_configuration_is_rejected(self):
        self.defaults.SMTPSSL_CERTFILE = '/tmp/nonexistent-cert'
        self.defaults.SMTPSSL_KEYFILE = None
        try:
            with patch.object(self.module.smtplib, 'SMTP', return_value=MagicMock()):
                conn = self.module.Connection()
                with self.assertRaises(ValueError):
                    conn.sendmail('alice@example.com', 'bob@example.com', 'Test')
        finally:
            self.defaults.SMTPSSL_CERTFILE = None

    def test_smtp_without_tls_does_not_create_context(self):
        self.defaults.SMTPSSL = False
        try:
            with patch.object(self.module.smtplib, 'SMTP', return_value=MagicMock()) as create, \
                    patch.object(self.module.ssl, 'create_default_context') as context:
                self.module.Connection().sendmail(
                    'alice@example.com', 'bob@example.com', 'Subject: Plain')
            context.assert_not_called()
            create.return_value.starttls.assert_not_called()
        finally:
            self.defaults.SMTPSSL = True


if __name__ == '__main__':
    unittest.main()
