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

"""Regression tests for the Python 3 filter parser and pipe rules."""

import dbm
import importlib
import pathlib
import pickle
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class FilterParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import TMDA
        cls.previous = getattr(TMDA, 'Defaults', None)
        defaults = types.ModuleType('TMDA.Defaults')
        cls.modules = patch.dict(sys.modules, {'TMDA.Defaults': defaults})
        cls.modules.start()
        TMDA.Defaults = defaults
        sys.modules.pop('TMDA.FilterParser', None)
        cls.module = importlib.import_module('TMDA.FilterParser')

    @classmethod
    def tearDownClass(cls):
        import TMDA
        sys.modules.pop('TMDA.FilterParser', None)
        if cls.previous is None:
            delattr(TMDA, 'Defaults')
        else:
            TMDA.Defaults = cls.previous
        cls.modules.stop()

    def test_original_incoming_filter_syntax(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'incoming')
            with open(path, 'w', encoding='utf-8') as fp:
                fp.write('from alice@example.com ok\nfrom * confirm\n')
            parser = self.module.FilterParser()
            parser.read(path)
            self.assertEqual(len(parser.filterlist), 2)


    def test_dbm_stored_action_uses_text_not_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'allow.dbm')
            with dbm.open(path, 'c') as database:
                database[b'sender@example.com'] = b'accept'
            parser = self.module.FilterParser()
            actions = {'incoming': ('hold', None)}
            found = parser._FilterParser__search_dbm(
                path, ['SENDER@EXAMPLE.COM'], actions, 'from-dbm')
            self.assertEqual(found, 1)
            self.assertEqual(actions['incoming'][0], 'accept')

    def test_dbm_no_match_preserves_default_action(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'allow.dbm')
            with dbm.open(path, 'c') as database:
                database[b'sender@example.com'] = b'accept'
            parser = self.module.FilterParser()
            actions = {'incoming': ('hold', None)}
            self.assertEqual(parser._FilterParser__search_dbm(
                path, ['another@example.com'], actions, 'from-dbm'), 0)
            self.assertEqual(actions['incoming'][0], 'hold')

    def test_pipe_rule_matching(self):
        parser = self.module.FilterParser()
        parser.filterlist = [
            ('pipe-headers', {}, 'exit 0', {'incoming': ('ok', None)}, 1),
        ]
        actions, line = parser.firstmatch('bob@example.com', msg_headers='X-Test: yes\r\n')
        self.assertTrue(actions)

    def test_pipe_rule_nonmatching(self):
        parser = self.module.FilterParser()
        parser.filterlist = [
            ('pipe-headers', {}, 'exit 1', {'incoming': ('ok', None)}, 1),
        ]
        actions, line = parser.firstmatch('bob@example.com', msg_headers='X-Test: yes\r\n')
        self.assertFalse(actions)


if __name__ == '__main__':
    unittest.main()
