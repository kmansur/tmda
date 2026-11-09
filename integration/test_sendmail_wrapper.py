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

"""Confirm that the original sendmail compatibility wrapper execs tmda-inject."""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WRAPPER = ROOT / 'bin' / 'tmda-sendmail'


class SendmailWrapperTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = pathlib.Path(self.directory.name)
        self.wrapper = self.path / 'tmda-sendmail'
        shutil.copyfile(WRAPPER, self.wrapper)
        self.inject = self.path / 'tmda-inject'
        self.inject.write_text(
            '#!' + sys.executable + '\n'
            'import json, os, sys\n'
            'print(json.dumps({"args": sys.argv[1:], '
            '"name": os.environ.get("NAME")}))\n',
            encoding='utf-8')
        self.inject.chmod(0o700)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(self.wrapper), *args],
            cwd=ROOT, capture_output=True, text=True,
            timeout=10)

    def test_explicit_recipients_pass_to_original_inject(self):
        result = self._run('-f', 'sender@example.org',
                           'alice@example.org', 'bob@example.org')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['args'],
                         ['alice@example.org', 'bob@example.org'])

    def test_t_option_discards_command_recipients_as_before(self):
        result = self._run('-t', 'alice@example.org')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['args'], [])

    def test_f_option_sets_original_sender_name(self):
        result = self._run('-F', 'Legacy Sender', 'alice@example.org')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout),
                         {'args': ['alice@example.org'],
                          'name': 'Legacy Sender'})


if __name__ == '__main__':
    unittest.main()
