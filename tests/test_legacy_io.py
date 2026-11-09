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
import dbm
import io
import os
import pickle
import sys
import tempfile
import types
from unittest.mock import patch
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


    def test_python2_eight_bit_pickle_cache_is_read(self):
        from TMDA import Util
        # Python 2 BINSTRING opcode with an original 0xff byte.
        old_pickle = b'\x80\x02U\x01\xffq\x00.'
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'pending.pickle')
            with open(path, 'wb') as fp:
                fp.write(old_pickle)
            self.assertEqual(Util.unpickle(path), '\xff')



    def test_cdb_autobuild_handles_python3_binary_keys(self):
        from TMDA import Util
        captured = []
        class Maker:
            def add(self, key, value):
                if not isinstance(key, bytes) or not isinstance(value, bytes):
                    raise TypeError('CDB Python 3 extension expects bytes')
                captured.append((key, value))
            def finish(self):
                pass
        stub = types.ModuleType('cdb')
        stub.cdbmake = lambda final, tmp: Maker()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'whitelist')
            with open(path, 'w', encoding='latin-1') as stream:
                stream.write('SENDER@example.com accept\n')
            with patch.dict(sys.modules, {'cdb': stub}):
                self.assertEqual(Util.build_cdb(path), 1)
        self.assertEqual(captured, [(b'sender@example.com', b'accept')])

    def test_dbm_autobuild_preserves_legacy_list_content(self):
        from TMDA import Util
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, 'whitelist')
            with open(filename, 'w', encoding='ascii') as fp:
                fp.write('sender@example.com accept\n')
            previous_tempdir = tempfile.tempdir
            self.assertEqual(Util.build_dbm(filename), 1)
            self.assertEqual(tempfile.tempdir, previous_tempdir)
            with dbm.open(filename + '.db', 'r') as database:
                self.assertEqual(database[b'sender@example.com'], b'accept')

    def test_pickle_writer_leaves_global_tempdir_unchanged(self):
        from TMDA import Util
        with tempfile.TemporaryDirectory() as directory:
            previous_tempdir = tempfile.tempdir
            Util.pickleit({'hello': 'world'},
                          os.path.join(directory, 'cache'))
            self.assertEqual(tempfile.tempdir, previous_tempdir)


    def test_legacy_list_readers_can_run_repeatedly(self):
        from TMDA import Util
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'whitelist')
            with open(path, 'w', encoding='ascii') as stream:
                stream.write('# comment\nALICE@example.com accept\n')
            for _ in range(3):
                self.assertEqual(
                    Util.file_to_list(path), ['ALICE@example.com accept'])
                self.assertEqual(
                    Util.file_to_dict(path, {}), {'alice@example.com': 'accept'})

    def test_legacy_list_append_deduplicates_and_closes_fileinput(self):
        from TMDA import Util
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'whitelist')
            with open(path, 'w', encoding='ascii') as stream:
                stream.write('# comment\nALICE@example.com\n')
            self.assertEqual(Util.append_to_file('alice@example.com', path), 0)
            for _ in range(3):
                Util.append_to_file('bob@example.com', path)
                self.assertIn('bob@example.com', Util.file_to_list(path))
            self.assertEqual(
                Util.file_to_list(path),
                ['ALICE@example.com', 'bob@example.com'])

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
