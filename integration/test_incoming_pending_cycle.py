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

"""Exercise the real incoming filter and pending CLI with private files."""

from email import policy
from email.message import EmailMessage
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = ROOT / 'bin'


class IncomingPendingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = pathlib.Path(self.temporary.name)
        data = self.home / '.tmda'
        data.mkdir()
        (data / 'crypt_key').write_text(
            '00112233445566778899aabbccddeeff00112233\n', encoding='ascii')
        (data / 'crypt_key').chmod(0o600)
        self.pending = data / 'pending'
        self.incoming = data / 'incoming'
        self.incoming.write_text('from * hold\n', encoding='ascii')
        config = data / 'config'
        config.write_text(
            'USERNAME = "alice"\n'
            'HOSTNAME = "example.com"\n'
            'MAIL_TRANSFER_AGENT = "qmail"\n'
            'DELIVERY = "_qok_"\n'
            'PENDING_QUEUE_FORMAT = "original"\n'
            'PENDING_CLEANUP_ODDS = 0\n'
            'PENDING_DIR = ' + repr(str(self.pending)) + '\n'
            'FILTER_INCOMING = ' + repr(str(self.incoming)) + '\n'
            'LOGFILE_INCOMING = None\n',
            encoding='utf-8')
        self.env = os.environ.copy()
        self.env.update({
            'HOME': str(self.home),
            'TMDARC': str(config),
            'GLOBAL_TMDARC': str(self.home / 'missing-global'),
            'SENDER': 'sender@example.net',
            'RECIPIENT': 'alice@example.com',
            'LOCAL': 'alice',
            'HOST': 'example.com',
            'EXT': '',
        })

    def _run(self, program, *args, data=None):
        return subprocess.run(
            [sys.executable, str(BIN / program), *args],
            input=data, cwd=ROOT, env=self.env,
            capture_output=True, timeout=15)

    def _incoming_message(self):
        msg = EmailMessage(policy=policy.SMTP)
        msg['From'] = 'sender@example.net'
        msg['To'] = 'alice@example.com'
        msg['Return-Path'] = '<sender@example.net>'
        msg['Subject'] = 'Pending cycle'
        msg.set_content('Preserve original message body.')
        return msg.as_bytes()

    def test_hold_then_list_then_delete(self):
        filtered = self._run('tmda-rfilter', data=self._incoming_message())
        self.assertIn(filtered.returncode, (0, 99), filtered.stderr.decode(
            'utf-8', errors='replace'))
        saved = list(self.pending.glob('*.msg'))
        self.assertEqual(len(saved), 1)
        self.assertIn(b'Preserve original message body.', saved[0].read_bytes())
        mailid = saved[0].name[:-4]
        listing = self._run('tmda-pending', '-b', '-T')
        self.assertEqual(listing.returncode, 0, listing.stderr.decode(
            'utf-8', errors='replace'))
        self.assertIn(mailid.encode('ascii'), listing.stdout)
        deleted = self._run('tmda-pending', '-b', '-d', mailid)
        self.assertEqual(deleted.returncode, 0, deleted.stderr.decode(
            'utf-8', errors='replace'))
        self.assertFalse(saved[0].exists())


if __name__ == '__main__':
    unittest.main()
