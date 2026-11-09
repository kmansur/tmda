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

"""Exercise the historical tmda-filter wrapper's exit handling."""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WRAPPER = ROOT / 'bin' / 'tmda-filter'


class FilterWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = pathlib.Path(self.temp.name)
        shutil.copyfile(WRAPPER, self.dir / 'tmda-filter')
        self.rfilter = self.dir / 'tmda-rfilter'
        self.env = os.environ.copy()
        self.env.update({
            'HOME': str(self.dir),
            'PYTHONPATH': str(ROOT) + os.pathsep + self.env.get('PYTHONPATH', ''),
            'TMDARC': str(self.dir / 'missing-config'),
            'GLOBAL_TMDARC': str(self.dir / 'missing-global'),
        })

    def _run(self):
        return subprocess.run(
            [sys.executable, str(self.dir / 'tmda-filter')],
            cwd=ROOT, env=self.env, capture_output=True, text=True,
            timeout=10)

    def test_original_tempfail_and_failure_report(self):
        self.rfilter.write_text(
            'raise RuntimeError("simulated incoming failure")\n',
            encoding='ascii')
        result = self._run()
        self.assertEqual(result.returncode, 75, result.stderr)
        report = self.dir / 'TMDA_DELIVERY_FAILURE'
        self.assertTrue(report.exists())
        self.assertIn('simulated incoming failure', report.read_text())

    def test_original_sys_exit_is_preserved(self):
        self.rfilter.write_text('raise SystemExit(99)\n', encoding='ascii')
        result = self._run()
        self.assertEqual(result.returncode, 99, result.stderr)
        self.assertFalse((self.dir / 'TMDA_DELIVERY_FAILURE').exists())


if __name__ == '__main__':
    unittest.main()
