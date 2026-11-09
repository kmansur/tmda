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

"""Exercise TMDA's real outgoing transports against disposable Postfix.

This test is executed only by the dedicated Postfix CI workflow.
The workflow creates a local-only Postfix instance and a dedicated
local mail recipient. No message is addressed outside localhost.
"""

from email import policy
from email.message import EmailMessage
import mailbox
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'bin' / 'tmda-inject'
RECIPIENT = 'tmda-ci@localhost'
MAILBOX = pathlib.Path('/var/mail/tmda-ci')


@unittest.skipUnless(os.environ.get('TMDA_TEST_LOCAL_POSTFIX') == '1',
                     'requires dedicated loopback-only Postfix CI environment')
class LocalPostfixDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name)
        datadir = self.home / '.tmda'
        datadir.mkdir()
        key = datadir / 'crypt_key'
        key.write_text('00112233445566778899aabbccddeeff00112233\n',
                       encoding='ascii')
        key.chmod(0o600)
        self.config = datadir / 'config'
        self.config.write_text(
            'USERNAME = "tmda-ci"\n'
            'HOSTNAME = "localhost"\n'
            'MAIL_TRANSFER_AGENT = "postfix"\n'
            'DELIVERY = "_qok_"\n'
            'ACTION_OUTGOING = "bare"\n'
            'MAIL_TRANSPORT = "sendmail"\n'
            'SENDMAIL_PROGRAM = "/usr/sbin/sendmail"\n'
            'FILTER_OUTGOING = ' + repr(str(datadir / 'no-filter')) + '\n'
            'LOGFILE_OUTGOING = None\n',
            encoding='utf-8')
        self.env = os.environ.copy()
        self.env['HOME'] = str(self.home)
        self.env['TMDARC'] = str(self.config)
        self.env['GLOBAL_TMDARC'] = str(self.home / 'missing-global')

    @staticmethod
    def _message(subject):
        msg = EmailMessage(policy=policy.SMTP)
        msg['From'] = 'tmda-ci@localhost'
        msg['To'] = RECIPIENT
        msg['Subject'] = subject
        msg.set_content('Postfix integration body')
        msg.add_attachment(b'\x00\xff\x80\x10',
                           maintype='application',
                           subtype='octet-stream',
                           filename='binary.dat')
        return msg.as_bytes()

    def _mailbox_contains(self, subject):
        if not MAILBOX.exists():
            return False
        inbox = mailbox.mbox(str(MAILBOX), create=False)
        try:
            for item in inbox:
                if item.get('Subject') == subject:
                    parts = list(item.walk())
                    self.assertEqual(
                        parts[-1].get_payload(decode=True),
                        b'\x00\xff\x80\x10')
                    return True
            return False
        finally:
            inbox.close()

    def _assert_delivered(self, subject):
        for attempt in range(30):
            if self._mailbox_contains(subject):
                return
            time.sleep(0.5)
        self.fail('Postfix did not deliver %s into local mailbox' % subject)

    def _inject(self, subject):
        return subprocess.run(
            [sys.executable, str(SCRIPT), RECIPIENT],
            input=self._message(subject), cwd=ROOT, env=self.env,
            capture_output=True, timeout=20)

    def test_sendmail_transport_local_delivery(self):
        subject = 'TMDA Postfix sendmail transport %d' % os.getpid()
        result = self._inject(subject)
        self.assertEqual(result.returncode, 0,
                         result.stderr.decode('utf-8', errors='replace'))
        self._assert_delivered(subject)

    def test_direct_smtp_transport_local_delivery(self):
        subject = 'TMDA Postfix direct SMTP %d' % os.getpid()
        with self.config.open('a', encoding='utf-8') as stream:
            stream.write(
                'MAIL_TRANSPORT = "smtp"\n'
                'SMTPHOST = "127.0.0.1:25"\n'
                'SMTPSSL = False\n')
        result = self._inject(subject)
        self.assertEqual(result.returncode, 0,
                         result.stderr.decode('utf-8', errors='replace'))
        self._assert_delivered(subject)


if __name__ == '__main__':
    unittest.main()
