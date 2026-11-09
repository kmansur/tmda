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

"""Test original smtp-check-sender without external DNS or SMTP traffic."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'contrib' / 'smtp-check-sender'

DNS_STUB = '''def DiscoverNameServers():
    pass

def mxlookup(domain):
    return [(10, "mx.example.org")]
'''

SMTP_STUB = '''import os
class SMTP:
    def __init__(self, host):
        if host != "mx.example.org":
            raise RuntimeError("Unexpected MX")
    def docmd(self, command, argument):
        if command == "rcpt to:":
            return int(os.environ["TMDA_TEST_RCPT_CODE"]), b"test reply"
        return 250, b"ok"
    def quit(self):
        return 221, b"bye"
'''


class SenderProbeCompatibilityTests(unittest.TestCase):
    def test_original_smtp_probe_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'DNS.py').write_text(DNS_STUB, encoding='ascii')
            (path / 'smtplib.py').write_text(SMTP_STUB, encoding='ascii')
            env = os.environ.copy()
            env['PYTHONPATH'] = str(path) + os.pathsep + env.get('PYTHONPATH', '')
            for code, expected_exit, expected_text in (
                    (250, 1, 'GOOD sender'),
                    (550, 0, 'BAD sender')):
                with self.subTest(reply=code):
                    env['TMDA_TEST_RCPT_CODE'] = str(code)
                    result = subprocess.run(
                        [sys.executable, str(SCRIPT), 'person@example.org'],
                        input='', capture_output=True, text=True,
                        cwd=ROOT, env=env, timeout=10)
                    self.assertEqual(result.returncode, expected_exit,
                                     result.stderr)
                    self.assertIn(expected_text, result.stdout)


if __name__ == '__main__':
    unittest.main()
