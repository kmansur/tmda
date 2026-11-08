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

"""Run tmda-inject against a private local sendmail capture executable."""

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'bin' / 'tmda-inject'


class TMDAInjectTests(unittest.TestCase):
    def test_mime_attachment_via_local_sendmail_capture(self):
        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            confdir = root / '.tmda'
            confdir.mkdir()
            (confdir / 'crypt_key').write_text(
                '00112233445566778899aabbccddeeff00112233\n', encoding='ascii')
            (confdir / 'crypt_key').chmod(0o600)
            capture = root / 'captured.eml'
            sendmail = root / 'fake-sendmail'
            sendmail.write_text(
                '#!' + sys.executable + '\n'
                'import os, sys\n'
                'with open(os.environ["TMDA_TEST_CAPTURE"], "wb") as fp:\n'
                '    fp.write(sys.stdin.buffer.read())\n',
                encoding='utf-8')
            sendmail.chmod(0o700)
            config = confdir / 'config'
            config.write_text(
                'MAIL_TRANSFER_AGENT = "postfix"\n'
                'DELIVERY = "_qok_"\n'
                'MAIL_TRANSPORT = "sendmail"\n'
                'SENDMAIL_PROGRAM = ' + repr(str(sendmail)) + '\n'
                'ACTION_OUTGOING = "bare"\n'
                'LOGFILE_OUTGOING = None\n'
                'FILTER_OUTGOING = ' + repr(str(confdir / 'no-filter')) + '\n',
                encoding='utf-8')
            msg = EmailMessage(policy=policy.SMTP)
            msg['From'] = 'alice@example.com'
            msg['To'] = 'bob@example.com'
            msg['Subject'] = 'MIME integration'
            msg.set_content('Plain section')
            msg.add_attachment(b'\x00\xff\x01', maintype='application',
                               subtype='octet-stream', filename='sample.bin')
            env = os.environ.copy()
            env['HOME'] = str(root)
            env['TMDARC'] = str(config)
            env['GLOBAL_TMDARC'] = str(root / 'missing-global-config')
            env['TMDA_TEST_CAPTURE'] = str(capture)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), 'bob@example.com'],
                input=msg.as_bytes(), cwd=ROOT, env=env,
                capture_output=True)
            self.assertEqual(result.returncode, 0,
                             result.stderr.decode('utf-8', errors='replace'))
            self.assertTrue(capture.exists())
            outgoing = BytesParser(policy=policy.default).parsebytes(
                capture.read_bytes())
            self.assertEqual(outgoing['To'], 'bob@example.com')
            self.assertEqual(
                next(outgoing.iter_attachments()).get_payload(decode=True),
                b'\x00\xff\x01')

            # A failing mail transport must not report successful delivery.
            sendmail.write_text(
                '#!' + sys.executable + '\n'
                'import sys\n'
                'sys.exit(75)\n',
                encoding='utf-8')
            failed = subprocess.run(
                [sys.executable, str(SCRIPT), 'bob@example.com'],
                input=msg.as_bytes(), cwd=ROOT, env=env,
                capture_output=True)
            self.assertNotEqual(failed.returncode, 0)



if __name__ == '__main__':
    unittest.main()
