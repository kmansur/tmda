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


    def test_hold_then_release_into_local_capture(self):
        fake_sendmail = self.home / 'fake-sendmail'
        capture = self.home / 'released.eml'
        fake_sendmail.write_text(
            '#!' + sys.executable + '\n'
            'import os, sys\n'
            'with open(os.environ["TMDA_TEST_RELEASE"], "wb") as stream:\n'
            '    stream.write(sys.stdin.buffer.read())\n',
            encoding='utf-8')
        fake_sendmail.chmod(0o700)
        config = pathlib.Path(self.env['TMDARC'])
        with config.open('a', encoding='utf-8') as stream:
            stream.write(
                'MAIL_TRANSPORT = "sendmail"\n'
                'SENDMAIL_PROGRAM = ' + repr(str(fake_sendmail)) + '\n')
        self.env['TMDA_TEST_RELEASE'] = str(capture)

        filtered = self._run('tmda-rfilter', data=self._incoming_message())
        self.assertIn(filtered.returncode, (0, 99), filtered.stderr.decode(
            'utf-8', errors='replace'))
        saved = list(self.pending.glob('*.msg'))
        self.assertEqual(len(saved), 1)
        mailid = saved[0].stem

        released = self._run('tmda-pending', '-b', '-r', mailid)
        self.assertEqual(released.returncode, 0, released.stderr.decode(
            'utf-8', errors='replace'))
        self.assertTrue(capture.exists())
        outgoing = capture.read_bytes()
        self.assertIn(b'X-TMDA-Confirm-Done:', outgoing)
        self.assertIn(b'X-TMDA-Released:', outgoing)
        self.assertIn(b'Preserve original message body.', outgoing)
        self.assertNotIn(b'X-TMDA-Recipient:', outgoing)


    def test_release_failure_does_not_delete_pending_message(self):
        fake_sendmail = self.home / 'rejected-sendmail'
        fake_sendmail.write_text(
            '#!' + sys.executable + '\n'
            'import sys\n'
            'sys.exit(75)\n',
            encoding='ascii')
        fake_sendmail.chmod(0o700)
        with pathlib.Path(self.env['TMDARC']).open(
                'a', encoding='utf-8') as stream:
            stream.write(
                'MAIL_TRANSPORT = "sendmail"\n'
                'SENDMAIL_PROGRAM = ' + repr(str(fake_sendmail)) + '\n')

        filtered = self._run('tmda-rfilter', data=self._incoming_message())
        self.assertIn(filtered.returncode, (0, 99))
        saved = list(self.pending.glob('*.msg'))
        self.assertEqual(len(saved), 1)
        before = saved[0].read_bytes()
        released = self._run('tmda-pending', '-b', '-r', saved[0].stem)
        self.assertNotEqual(released.returncode, 0)
        self.assertTrue(saved[0].exists())
        self.assertEqual(saved[0].read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
