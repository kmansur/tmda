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


    def test_maildir_hold_list_and_delete(self):
        with pathlib.Path(self.env['TMDARC']).open(
                'a', encoding='utf-8') as stream:
            stream.write('PENDING_QUEUE_FORMAT = "maildir"\n')
        filtered = self._run('tmda-rfilter', data=self._incoming_message())
        self.assertIn(filtered.returncode, (0, 99), filtered.stderr.decode(
            'utf-8', errors='replace'))
        newdir = self.pending / 'new'
        saved = list(newdir.iterdir())
        self.assertEqual(len(saved), 1)
        mailid = '.'.join(saved[0].name.split('.')[:2])
        listing = self._run('tmda-pending', '-b', '-T')
        self.assertEqual(listing.returncode, 0, listing.stderr.decode(
            'utf-8', errors='replace'))
        self.assertIn(mailid.encode('ascii'), listing.stdout)
        deleted = self._run('tmda-pending', '-b', '-d', mailid)
        self.assertEqual(deleted.returncode, 0, deleted.stderr.decode(
            'utf-8', errors='replace'))
        self.assertFalse(saved[0].exists())


    def test_legacy_confirm_cookie_releases_and_cleans_queue(self):
        """Original hold, valid address confirmation, and done-header cycle."""
        fake_sendmail = self.home / 'fake-confirm-sendmail'
        capture = self.home / 'confirmed.eml'
        fake_sendmail.write_text(
            '#!' + sys.executable + '\n'
            'import os, sys\n'
            'with open(os.environ["TMDA_TEST_RELEASE"], "wb") as output:\n'
            '    output.write(sys.stdin.buffer.read())\n',
            encoding='utf-8')
        fake_sendmail.chmod(0o700)
        with pathlib.Path(self.env['TMDARC']).open(
                'a', encoding='utf-8') as stream:
            stream.write(
                'MAIL_TRANSPORT = "sendmail"\n'
                'SENDMAIL_PROGRAM = ' + repr(str(fake_sendmail)) + '\n')
        self.env['TMDA_TEST_RELEASE'] = str(capture)
        original = self._incoming_message()

        held = self._run('tmda-rfilter', data=original)
        self.assertIn(held.returncode, (0, 99),
                      held.stderr.decode('utf-8', errors='replace'))
        files = list(self.pending.glob('*.msg'))
        self.assertEqual(len(files), 1)
        mailid = files[0].stem
        timestamp, pid = mailid.split('.')
        key = subprocess.run(
            [sys.executable, '-c',
             'from TMDA import Cookie; '
             'import sys; print(Cookie.make_confirm_cookie('
             'sys.argv[1],sys.argv[2],"accept"))',
             timestamp, pid],
            cwd=ROOT, env=self.env, capture_output=True,
            text=True, timeout=10)
        self.assertEqual(key.returncode, 0, key.stderr)
        cookie = key.stdout.strip()

        confirmed_env = self.env.copy()
        confirmed_env['EXT'] = 'confirm-' + cookie
        confirmed_env['RECIPIENT'] = 'alice-confirm-' + cookie + '@example.com'
        confirmation = EmailMessage(policy=policy.SMTP)
        confirmation['From'] = 'sender@example.net'
        confirmation['To'] = confirmed_env['RECIPIENT']
        confirmation['Subject'] = 'Confirm the pending message'
        confirmation.set_content('Confirmation response')
        released = subprocess.run(
            [sys.executable, str(BIN / 'tmda-rfilter')],
            cwd=ROOT, env=confirmed_env, capture_output=True,
            input=confirmation.as_bytes(), timeout=15)
        self.assertIn(released.returncode, (0, 99),
                      released.stderr.decode('utf-8', errors='replace'))
        self.assertTrue(capture.exists())
        reinjected = capture.read_bytes()
        self.assertIn(b'X-TMDA-Confirm-Done:', reinjected)
        self.assertIn(b'Preserve original message body.', reinjected)

        accepted = self._run('tmda-rfilter', data=reinjected)
        self.assertEqual(accepted.returncode, 0,
                         accepted.stderr.decode('utf-8', errors='replace'))
        self.assertFalse(files[0].exists())



    def test_original_confirmation_request_generates_reply_address(self):
        self.incoming.write_text('from * confirm\n', encoding='ascii')
        fake_sendmail = self.home / 'fake-request-sendmail'
        capture = self.home / 'request.eml'
        fake_sendmail.write_text(
            '#!' + sys.executable + '\n'
            'import os, sys\n'
            'with open(os.environ["TMDA_TEST_RELEASE"], "wb") as output:\n'
            '    output.write(sys.stdin.buffer.read())\n',
            encoding='ascii')
        fake_sendmail.chmod(0o700)
        with pathlib.Path(self.env['TMDARC']).open(
                'a', encoding='utf-8') as stream:
            stream.write(
                'MAIL_TRANSPORT = "sendmail"\n'
                'SENDMAIL_PROGRAM = ' + repr(str(fake_sendmail)) + '\n'
                'TEMPLATE_DIR = ' + repr(str(ROOT / 'templates')) + '\n'
                'MAX_AUTORESPONSES_PER_DAY = 0\n'
                'AUTORESPONSE_INCLUDE_SENDER_COPY = 1\n')
        self.env['TMDA_TEST_RELEASE'] = str(capture)
        result = self._run('tmda-rfilter', data=self._incoming_message())
        self.assertIn(result.returncode, (0, 99),
                      result.stderr.decode('utf-8', errors='replace'))
        self.assertEqual(len(list(self.pending.glob('*.msg'))), 1)
        self.assertTrue(capture.exists())
        generated = capture.read_bytes()
        self.assertIn(b'Please confirm your message', generated)
        self.assertIn(b'Original Message Headers', generated)
        self.assertIn(b'alice-confirm-', generated)



    def test_autoresponse_rate_limit_and_expired_record_cleanup(self):
        """Original rate limiting records must not alter relative mail paths."""
        import time

        response_dir = self.home / '.tmda' / 'responses'
        response_dir.mkdir()
        old_record = response_dir / '1000000000.999.sender@example.net'
        old_record.write_text('', encoding='ascii')

        self.incoming.write_text('from * confirm\n', encoding='ascii')
        fake_sendmail = self.home / 'fake-rate-sendmail'
        deliveries = self.home / 'outgoing-count'
        fake_sendmail.write_text(
            '#!' + sys.executable + '\n'
            'import os, pathlib, sys\n'
            'sys.stdin.buffer.read()\n'
            'path = pathlib.Path(os.environ["TMDA_TEST_COUNTER"])\n'
            'with path.open("a", encoding="ascii") as stream:\n'
            '    stream.write("1\\n")\n',
            encoding='ascii')
        fake_sendmail.chmod(0o700)
        with pathlib.Path(self.env['TMDARC']).open(
                'a', encoding='utf-8') as stream:
            stream.write(
                'MAIL_TRANSPORT = "sendmail"\n'
                'SENDMAIL_PROGRAM = ' + repr(str(fake_sendmail)) + '\n'
                'TEMPLATE_DIR = ' + repr(str(ROOT / 'templates')) + '\n'
                'RESPONSE_DIR = ' + repr(str(response_dir)) + '\n'
                'MAX_AUTORESPONSES_PER_DAY = 1\n'
                'AUTORESPONSE_INCLUDE_SENDER_COPY = 0\n')
        self.env['TMDA_TEST_COUNTER'] = str(deliveries)

        first = self._run('tmda-rfilter', data=self._incoming_message())
        self.assertIn(first.returncode, (0, 99),
                      first.stderr.decode('utf-8', errors='replace'))
        self.assertFalse(old_record.exists())
        self.assertTrue(deliveries.exists())
        self.assertEqual(len(deliveries.read_text().splitlines()), 1)
        self.assertEqual(len(list(response_dir.iterdir())), 1)

        second = self._run('tmda-rfilter', data=self._incoming_message())
        self.assertIn(second.returncode, (0, 99),
                      second.stderr.decode('utf-8', errors='replace'))
        self.assertEqual(len(deliveries.read_text().splitlines()), 1)
        self.assertEqual(len(list(response_dir.iterdir())), 1)


    def test_interactive_pending_delete_keeps_legacy_prompt(self):
        held = self._run('tmda-rfilter', data=self._incoming_message())
        self.assertIn(held.returncode, (0, 99),
                      held.stderr.decode('utf-8', errors='replace'))
        messages = list(self.pending.glob('*.msg'))
        self.assertEqual(len(messages), 1)
        interactive = self._run(
            'tmda-pending', messages[0].stem, data=b'd\n')
        self.assertEqual(interactive.returncode, 0,
                         interactive.stderr.decode('utf-8', errors='replace'))
        self.assertIn(b'[d]el', interactive.stdout)
        self.assertFalse(messages[0].exists())

    def test_interactive_pending_quit_preserves_message(self):
        held = self._run('tmda-rfilter', data=self._incoming_message())
        self.assertIn(held.returncode, (0, 99),
                      held.stderr.decode('utf-8', errors='replace'))
        messages = list(self.pending.glob('*.msg'))
        self.assertEqual(len(messages), 1)
        interactive = self._run(
            'tmda-pending', messages[0].stem, data=b'q\n')
        self.assertEqual(interactive.returncode, 0,
                         interactive.stderr.decode('utf-8', errors='replace'))
        self.assertTrue(messages[0].exists())


    def test_legacy_pending_cache_hides_already_seen_messages(self):
        held = self._run('tmda-rfilter', data=self._incoming_message())
        self.assertIn(held.returncode, (0, 99),
                      held.stderr.decode('utf-8', errors='replace'))
        messages = list(self.pending.glob('*.msg'))
        self.assertEqual(len(messages), 1)
        mailid = messages[0].stem.encode('ascii')
        first = self._run('tmda-pending', '-b', '-C', '-T')
        self.assertEqual(first.returncode, 0,
                         first.stderr.decode('utf-8', errors='replace'))
        self.assertIn(mailid, first.stdout)
        cache = self.home / '.tmda' / '.pendingcache'
        self.assertTrue(cache.exists())
        second = self._run('tmda-pending', '-b', '-C', '-T')
        self.assertEqual(second.returncode, 0,
                         second.stderr.decode('utf-8', errors='replace'))
        self.assertNotIn(mailid, second.stdout)
        self.assertTrue(messages[0].exists())


if __name__ == '__main__':
    unittest.main()
