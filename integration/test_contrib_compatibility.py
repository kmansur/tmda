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

"""Exercise the original optional contrib tools against Python 3."""

import dbm
from email.message import EmailMessage
import mailbox
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRIB = ROOT / 'contrib'


class ContribCompatibilityTests(unittest.TestCase):
    def _run(self, program, *args, cwd=None, data=None):
        return subprocess.run(
            [sys.executable, str(CONTRIB / program), *args],
            cwd=cwd or ROOT, input=data,
            capture_output=True, text=True, timeout=10)

    @staticmethod
    def _message(address):
        msg = EmailMessage()
        msg['From'] = address
        msg['To'] = 'local@example.com'
        msg.set_content('mailbox message')
        return msg

    def test_collectaddys_reads_mbox_and_maildir(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            mbox = mailbox.mbox(str(root / 'archive.mbox'))
            mbox.add(self._message('Person <FIRST@EXAMPLE.COM>'))
            mbox.flush()
            mbox.close()
            maildir = mailbox.Maildir(str(root / 'Maildir'))
            maildir.add(self._message('Other <second@example.com>'))
            maildir.close()
            result = self._run('collectaddys', cwd=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            addresses = result.stdout.splitlines()
            self.assertIn('first@example.com', addresses)
            self.assertIn('second@example.com', addresses)
            self.assertEqual(addresses.count('first@example.com'), 1)

    def test_printdbm_preserves_key_value_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(pathlib.Path(directory) / 'legacy')
            with dbm.open(path, 'c') as database:
                database[b'alice@example.com'] = b'ALLOW'
            result = self._run('printdbm', path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('alice@example.com ALLOW', result.stdout)

    def test_def2html_sorts_defaults_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'Defaults.py'
            path.write_text(
                '# ZZZ_OPTION\n# An option\nZZZ_OPTION = 1\n'
                '# AAA_OPTION\n# Another option\nAAA_OPTION = 2\n',
                encoding='utf-8')
            for args in ((str(path),), ('--css', str(path))):
                result = self._run('def2html', *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('AAA_OPTION', result.stdout)
                self.assertLess(result.stdout.index('AAA_OPTION'),
                                result.stdout.index('ZZZ_OPTION'))


if __name__ == '__main__':
    unittest.main()
