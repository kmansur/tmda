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

"""Regression tests for Python 3 subprocess and pending file I/O."""

import contextlib
import io
import os
import pickle
import sys
import tempfile
import unittest


class UtilityTests(unittest.TestCase):
    def test_pickle_protocol_two_round_trip(self):
        from TMDA import Util
        value = {'sender': 'alice@example.com', 'count': 2}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'pending.pickle')
            Util.pickleit(value, path)
            with open(path, 'rb') as fp:
                self.assertEqual(fp.read(2), b'\x80\x02')
            self.assertEqual(Util.unpickle(path), value)

    def test_legacy_pickle_file_read(self):
        from TMDA import Util
        value = {'mailid': '1700000000.123'}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'pending.pickle')
            with open(path, 'wb') as fp:
                pickle.dump(value, fp, protocol=2)
            self.assertEqual(Util.unpickle(path), value)

    def test_pipecmd_writes_original_message_bytes(self):
        from TMDA import Util
        code = ('import sys; data=sys.stdin.buffer.read(); '
                'sys.exit(0 if data == bytes([65, 255, 66]) else 3)')
        Util.pipecmd([sys.executable, '-c', code], 'A\xffB')

    def test_pipecmd_reports_failure(self):
        from TMDA import Util
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(IOError):
                Util.pipecmd([sys.executable, '-c', 'import sys; sys.exit(7)'])


if __name__ == '__main__':
    unittest.main()
