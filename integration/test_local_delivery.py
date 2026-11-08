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

"""Verify local delivery formats without any external mail delivery."""

import importlib
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class LocalDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import TMDA
        cls.previous_defaults = getattr(TMDA, 'Defaults', None)
        cls.defaults = types.ModuleType('TMDA.Defaults')
        cls.modules = patch.dict(sys.modules, {'TMDA.Defaults': cls.defaults})
        cls.modules.start()
        TMDA.Defaults = cls.defaults
        sys.modules.pop('TMDA.Deliver', None)
        cls.Deliver = importlib.import_module('TMDA.Deliver').Deliver

    @classmethod
    def tearDownClass(cls):
        import TMDA
        sys.modules.pop('TMDA.Deliver', None)
        if cls.previous_defaults is None:
            delattr(TMDA, 'Defaults')
        else:
            TMDA.Defaults = cls.previous_defaults
        cls.modules.stop()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.deliver = object.__new__(self.Deliver)

    def test_maildir_local_delivery_preserves_eight_bit_message(self):
        root = pathlib.Path(self.tmp.name) / 'Maildir'
        for name in ('tmp', 'new', 'cur'):
            (root / name).mkdir(parents=True, exist_ok=True)
        self.deliver._Deliver__deliver_maildir('Subject: Test\n\nA\xffB', str(root))
        files = list((root / 'new').iterdir())
        self.assertEqual(len(files), 1)
        self.assertIn(b'A\xffB', files[0].read_bytes())
        self.assertFalse(list((root / 'tmp').iterdir()))

    def test_mbox_local_delivery_preserves_eight_bit_message(self):
        path = pathlib.Path(self.tmp.name) / 'mailbox'
        path.write_bytes(b'')
        self.deliver._Deliver__deliver_mbox(
            'From alice@example.com Sat Nov 08 12:00:00 2026\nSubject: Test\n\nA\xffB', str(path))
        self.assertIn(b'A\xffB\n\n', path.read_bytes())

    def test_mmdf_local_delivery_preserves_message(self):
        path = pathlib.Path(self.tmp.name) / 'mailbox.mmdf'
        path.write_bytes(b'')
        self.deliver._Deliver__deliver_mmdf('Subject: Test\n\nHello', str(path))
        data = path.read_bytes()
        self.assertTrue(data.startswith(b'\x01\x01\x01\x01\n'))
        self.assertIn(b'Subject: Test\n\nHello', data)
        self.assertTrue(data.endswith(b'\x01\x01\x01\x01\n'))


if __name__ == '__main__':
    unittest.main()
