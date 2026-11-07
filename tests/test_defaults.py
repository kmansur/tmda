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

"""Check legacy defaults against an isolated, non-production home."""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class DefaultsTests(unittest.TestCase):
    def test_defaults_import_with_legacy_secret_key(self):
        with tempfile.TemporaryDirectory() as home:
            datadir = pathlib.Path(home) / '.tmda'
            datadir.mkdir()
            keyfile = datadir / 'crypt_key'
            keyfile.write_text('00112233445566778899aabbccddeeff00112233\n', encoding='ascii')
            keyfile.chmod(0o600)
            env = os.environ.copy()
            env['HOME'] = home
            env['TMDARC'] = str(datadir / 'absent-config')
            env['GLOBAL_TMDARC'] = str(datadir / 'absent-global-config')
            result = subprocess.run(
                [sys.executable, '-c',
                 'from TMDA import Defaults; '
                 'assert Defaults.CRYPT_KEY.hex() == '
                 '"00112233445566778899aabbccddeeff00112233"'],
                cwd=ROOT, env=env, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
