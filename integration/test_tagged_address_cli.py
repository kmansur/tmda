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

"""Check tagged addresses using the real command-line programs."""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = ROOT / 'bin'


class TaggedAddressCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        tmda = root / '.tmda'
        tmda.mkdir()
        (tmda / 'crypt_key').write_text(
            '00112233445566778899aabbccddeeff00112233\n', encoding='ascii')
        (tmda / 'crypt_key').chmod(0o600)
        config = tmda / 'config'
        config.write_text('USERNAME = "alice"\nHOSTNAME = "example.com"\n',
                          encoding='ascii')
        self.env = os.environ.copy()
        self.env['HOME'] = str(root)
        self.env['TMDARC'] = str(config)
        self.env['GLOBAL_TMDARC'] = str(root / 'missing-global')

    def _run(self, name, *args):
        return subprocess.run([sys.executable, str(BIN / name), *args],
                              cwd=ROOT, env=self.env, capture_output=True,
                              text=True, timeout=10)

    def test_keyword_address_cli_round_trip(self):
        generated = self._run('tmda-address', '-a', 'alice@example.com',
                              '-k', 'newsletter')
        self.assertEqual(generated.returncode, 0, generated.stderr)
        address = generated.stdout.strip()
        self.assertIn('-keyword-', address)
        verified = self._run('tmda-check-address', address)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertIn('STATUS: VALID', verified.stdout)

    def test_dated_address_cli_round_trip(self):
        generated = self._run('tmda-address', '-a', 'alice@example.com',
                              '-d', '-t', '1d')
        self.assertEqual(generated.returncode, 0, generated.stderr)
        verified = self._run('tmda-check-address', generated.stdout.strip())
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertIn('STATUS: VALID', verified.stdout)
        self.assertIn('EXPIRES:', verified.stdout)


if __name__ == '__main__':
    unittest.main()
