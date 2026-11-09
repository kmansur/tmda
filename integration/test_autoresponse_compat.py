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

"""Run the original auto-response generator for each supported copy mode."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r'''
from email import message_from_string
from TMDA import AutoResponse, Defaults, Util
import sys
Defaults.AUTORESPONSE_INCLUDE_SENDER_COPY = int(sys.argv[1])
Defaults.CONFIRM_MAX_MESSAGE_SIZE = 100000
incoming = message_from_string(
    'From: sender@example.org\n'
    'To: recipient@example.org\n'
    'Message-ID: <legacy@example.org>\n'
    'Subject: Original\n'
    '\nOriginal message body\n')
template = (
    'From: recipient@example.org\n'
    'Subject: Confirmation requested\n'
    '\nPlease confirm your message.\n')
response = AutoResponse.AutoResponse(
    incoming, template, 'request', 'sender@example.org')
response.create()
output = Util.msg_as_string(response.mimemsg)
assert 'Confirmation requested' in output
assert 'Please confirm your message.' in output
if int(sys.argv[1]) == 0:
    assert 'multipart/mixed' not in output
else:
    assert 'multipart/mixed' in output
    assert 'Original Message' in output or 'Original Message Headers' in output
if int(sys.argv[1]) == 2:
    assert 'Original message body' in output
print('autoresponse mode', sys.argv[1], 'ok')
'''


class AutoResponseCompatibilityTests(unittest.TestCase):
    def test_all_legacy_sender_copy_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            tmda = Path(directory) / '.tmda'
            tmda.mkdir()
            key = tmda / 'crypt_key'
            key.write_text('00112233445566778899aabbccddeeff00112233\n',
                           encoding='ascii')
            key.chmod(0o600)
            config = tmda / 'config'
            config.write_text(
                'USERNAME = "recipient"\n'
                'HOSTNAME = "example.org"\n'
                'MAIL_TRANSFER_AGENT = "qmail"\n'
                'DELIVERY = "_qok_"\n', encoding='ascii')
            env = os.environ.copy()
            env.update({
                'HOME': directory,
                'TMDARC': str(config),
                'GLOBAL_TMDARC': str(tmda / 'nonexistent-global'),
            })
            for mode in (0, 1, 2):
                with self.subTest(include_sender_copy=mode):
                    outcome = subprocess.run(
                        [sys.executable, '-c', SCRIPT, str(mode)],
                        cwd=ROOT, env=env, capture_output=True, text=True,
                        timeout=10)
                    self.assertEqual(outcome.returncode, 0, outcome.stderr)


if __name__ == '__main__':
    unittest.main()
