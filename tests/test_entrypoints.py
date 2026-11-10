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

"""Check command-line entry points without touching the user's mail."""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = ROOT / 'bin'
VERSION_ENTRYPOINTS = (
    'tmda-address',
    'tmda-check-address',
    'tmda-inject',
    'tmda-keygen',
    'tmda-ofmipd',
    'tmda-pending',
    'tmda-rfilter',
)


class EntrypointTests(unittest.TestCase):
    def test_version_without_live_configuration(self):
        with tempfile.TemporaryDirectory() as home:
            env = os.environ.copy()
            env['HOME'] = home
            env['TMDARC'] = str(pathlib.Path(home) / 'missing-config')
            env['GLOBAL_TMDARC'] = str(pathlib.Path(home) / 'missing-global')
            for name in VERSION_ENTRYPOINTS:
                with self.subTest(program=name):
                    result = subprocess.run(
                        [sys.executable, str(BIN / name), '-V'],
                        cwd=ROOT, env=env, capture_output=True, text=True,
                        timeout=10)
                    self.assertEqual(result.returncode, 0,
                                     name + ': ' + result.stderr)
                    self.assertIn('TMDA/1.1.12', result.stdout)


    def test_sendmail_compatibility_wrapper_version_and_help(self):
        with tempfile.TemporaryDirectory() as home:
            env = os.environ.copy()
            env['HOME'] = home
            env['TMDARC'] = str(pathlib.Path(home) / 'missing-config')
            for arguments, expected in (
                (['-V'], 'TMDA/1.1.12'),
                (['--version'], '1.1.12'),
                (['-h'], 'Sendmail compatibility wrapper'),
            ):
                with self.subTest(arguments=arguments):
                    result = subprocess.run(
                        [sys.executable, str(BIN / 'tmda-sendmail')] + arguments,
                        cwd=ROOT, env=env, capture_output=True, text=True,
                        timeout=10,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(expected, result.stdout)

    def test_sendmail_wrapper_rejects_invalid_option_without_delivery(self):
        with tempfile.TemporaryDirectory() as home:
            env = os.environ.copy()
            env['HOME'] = home
            env['TMDARC'] = str(pathlib.Path(home) / 'missing-config')
            result = subprocess.run(
                [sys.executable, str(BIN / 'tmda-sendmail'), '--invalid-option'],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('option --invalid-option not recognized',
                          result.stdout)



if __name__ == '__main__':
    unittest.main()
