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

"""Exercise the historical SMTP proxy on an isolated loopback socket."""

import asyncore
import contextlib
import io
import os
import pathlib
import runpy
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'bin' / 'tmda-ofmipd'


class SMTPLoopbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Avoid the __main__ entry point and any production configuration.
        with patch.object(sys, 'argv', [str(SCRIPT), '--foreground']):
            with contextlib.redirect_stderr(io.StringIO()):
                cls.proxy = runpy.run_path(str(SCRIPT), run_name='tmda_loopback_test')
        cls.proxy['opts'].ssl = False
        cls.proxy['opts'].tls = None
        cls.proxy['opts'].debug = False
        cls.proxy['opts'].one_session = False
        cls.proxy['opts'].throttlescript = None
        cls.proxy['opts'].authprog = None
        cls.proxy['remoteauth']['enable'] = 0

    def setUp(self):
        self.received = []
        def capture_message(*args):
            self.received.append(args)
            return None
        self.server = self.proxy['SMTPServer'](
            ('127.0.0.1', 0), capture_message)
        self.client = socket.create_connection(self.server.socket.getsockname(), timeout=2)
        self.client.setblocking(False)
        self._pump()
        self.assertTrue(self._read().startswith(b'220 '))

    def tearDown(self):
        self.client.close()
        asyncore.close_all()

    def _pump(self):
        for _ in range(12):
            asyncore.loop(timeout=0.005, count=1)

    def _read(self):
        output = b''
        for _ in range(40):
            self._pump()
            try:
                chunk = self.client.recv(8192)
            except BlockingIOError:
                chunk = b''
            if chunk:
                output += chunk
                if output.endswith(b'\r\n'):
                    return output
        return output

    def _command(self, value):
        self.client.sendall(value + b'\r\n')
        return self._read()

    def test_ehlo_noop_quit(self):
        response = self._command(b'EHLO local.example')
        self.assertIn(b'250-', response)
        self.assertIn(b'AUTH', response)
        self.assertEqual(self._command(b'NOOP'), b'250 Ok\r\n')
        self.assertEqual(self._command(b'QUIT'), b'221 Bye\r\n')

    def test_reject_mail_before_authentication(self):
        self.assertTrue(self._command(b'MAIL FROM:<alice@example.com>').startswith(b'530 '))

    def test_auth_login_and_rejected_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'auth'
            path.write_text('alice:secret\n', encoding='ascii')
            self.proxy['opts'].authfile = str(path)
            self.assertIn(b'250-', self._command(b'EHLO local.example'))
            self.assertEqual(self._command(b'AUTH LOGIN'), b'334 VXNlcm5hbWU6\r\n')
            self.assertEqual(self._command(b'YWxpY2U='), b'334 UGFzc3dvcmQ6\r\n')
            self.assertEqual(self._command(b'd3Jvbmc='), b'535 AUTH failed\r\n')


    def test_authenticated_smtp_data_without_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'auth'
            path.write_text('alice:secret\n', encoding='ascii')
            self.proxy['opts'].authfile = str(path)
            self.assertIn(b'AUTH', self._command(b'EHLO local.example'))
            self.assertEqual(self._command(b'AUTH LOGIN'), b'334 VXNlcm5hbWU6\r\n')
            self.assertEqual(self._command(b'YWxpY2U='), b'334 UGFzc3dvcmQ6\r\n')
            self.assertEqual(self._command(b'c2VjcmV0'), b'235 AUTH successful\r\n')
            self.assertEqual(self._command(b'MAIL FROM:<alice@example.com>'), b'250 Ok\r\n')
            self.assertEqual(self._command(b'RCPT TO:<bob@example.com>'), b'250 Ok\r\n')
            self.assertTrue(self._command(b'DATA').startswith(b'354 '))
            self.client.sendall(b'Subject: Test\r\n\r\nHello\r\n.\r\n')
            self.assertEqual(self._read(), b'250 Ok\r\n')
            self.assertEqual(len(self.received), 1)
            peer, sender, recipients, message, username = self.received[0]
            self.assertEqual(sender, 'alice@example.com')
            self.assertEqual(recipients, ['bob@example.com'])
            self.assertEqual(username, 'alice')
            self.assertIn('Subject: Test', message)
            self.assertIn('Hello', message)


if __name__ == '__main__':
    unittest.main()
