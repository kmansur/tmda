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

"""Exercise implicit TLS using an isolated SMTP socket and test certificate."""

import asyncore
import contextlib
import io
import pathlib
import runpy
import socket
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'bin' / 'tmda-ofmipd'


class SMTPImplicitTLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cert = pathlib.Path(cls.tmp.name) / 'cert.pem'
        key = pathlib.Path(cls.tmp.name) / 'key.pem'
        subprocess.run(
            ['openssl', 'req', '-x509', '-nodes', '-newkey', 'rsa:2048',
             '-days', '1', '-subj', '/CN=localhost',
             '-keyout', str(key), '-out', str(cert)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with patch.object(sys, 'argv', [str(SCRIPT), '--foreground', '--ssl',
                                        '--ssl-cert', str(cert), '--ssl-key', str(key)]):
            with contextlib.redirect_stderr(io.StringIO()):
                cls.proxy = runpy.run_path(str(SCRIPT), run_name='tmda_implicit_tls_test')
        cls.proxy['opts'].debug = False
        cls.proxy['opts'].authprog = None
        cls.proxy['remoteauth']['enable'] = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.server = self.proxy['SMTPServer'](
            ('127.0.0.1', 0), lambda *args: '451 Disabled in test')
        raw = socket.create_connection(self.server.socket.getsockname(), timeout=2)
        raw.setblocking(False)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        self.client = context.wrap_socket(
            raw, server_hostname='localhost', do_handshake_on_connect=False)
        for _ in range(160):
            self._pump()
            try:
                self.client.do_handshake()
                break
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                continue
        else:
            self.fail('Implicit TLS handshake did not complete')
        self.assertTrue(self._read().startswith(b'220 '))

    def tearDown(self):
        self.client.close()
        asyncore.close_all()

    def _pump(self):
        for _ in range(15):
            asyncore.loop(timeout=0.005, count=1)

    def _read(self):
        output = b''
        for _ in range(60):
            self._pump()
            try:
                part = self.client.recv(8192)
            except (BlockingIOError, ssl.SSLWantReadError, ssl.SSLWantWriteError):
                part = b''
            if part:
                output += part
                if output.endswith(b'\r\n'):
                    if output.startswith(b'250-') and b'\r\n250 ' not in output:
                        continue
                    return output
        return output

    def _command(self, value):
        self.client.sendall(value + b'\r\n')
        return self._read()

    def test_implicit_tls_smtp_greeting(self):
        self.assertIn(self.client.version(), ('TLSv1.2', 'TLSv1.3'))
        self.assertIn(b'AUTH ', self._command(b'EHLO localhost'))
        self.assertEqual(self._command(b'NOOP'), b'250 Ok\r\n')
        self.assertEqual(self._command(b'QUIT'), b'221 Bye\r\n')


if __name__ == '__main__':
    unittest.main()
