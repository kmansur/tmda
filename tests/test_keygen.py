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

"""Regression tests for the original TMDA key-generation interface."""

import pathlib
import re
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class KeygenTests(unittest.TestCase):
    def test_batch_key_is_160_bit_hex(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / 'bin' / 'tmda-keygen'), '--batch'],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertRegex(result.stdout.strip(), r'^[0-9a-f]{40}$')
        self.assertEqual(result.stderr, '')

    def test_version_option(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / 'bin' / 'tmda-keygen'), '-V'],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn('TMDA/1.1.12', result.stdout)


if __name__ == '__main__':
    unittest.main()
