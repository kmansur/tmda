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

"""Exercise pending queues without a production TMDA configuration."""

from email.message import EmailMessage
from email.parser import Parser
import importlib
import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class PendingQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import TMDA
        cls.saved_defaults = getattr(TMDA, 'Defaults', None)
        cls.defaults = types.ModuleType('TMDA.Defaults')
        cls.modules = patch.dict(sys.modules, {'TMDA.Defaults': cls.defaults})
        cls.modules.start()
        TMDA.Defaults = cls.defaults
        from TMDA.Queue.OriginalQueue import OriginalQueue
        from TMDA.Queue.MaildirQueue import MaildirQueue
        cls.OriginalQueue = OriginalQueue
        cls.MaildirQueue = MaildirQueue

    @classmethod
    def tearDownClass(cls):
        import TMDA
        if cls.saved_defaults is None:
            delattr(TMDA, 'Defaults')
        else:
            TMDA.Defaults = cls.saved_defaults
        cls.modules.stop()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.defaults.PENDING_DIR = str(pathlib.Path(self.tmp.name) / 'pending')
        self.defaults.PENDING_LIFETIME = '7d'
        self.defaults.PENDING_DELETE_APPEND = None

    def _message(self):
        msg = EmailMessage()
        msg['From'] = 'alice@example.com'
        msg['To'] = 'bob@example.com'
        msg['Subject'] = 'Queue integration'
        msg.set_content('Pending message')
        return msg

    def test_original_queue_round_trip(self):
        queue = self.OriginalQueue()
        mailid = '1700000000.123'
        msg = self._message()
        queue.insert_message(msg, mailid, 'bob@example.com')
        self.assertTrue(queue.find_message(mailid))
        self.assertEqual(queue.fetch_ids(), [mailid])
        fetched = queue.fetch_message(mailid)
        self.assertEqual(fetched['X-TMDA-Recipient'], 'bob@example.com')
        self.assertIn('Pending message', fetched.get_payload())
        self.assertIsNone(msg.get('X-TMDA-Recipient'))
        queue.delete_message(mailid)
        self.assertFalse(queue.find_message(mailid))

    def test_maildir_queue_round_trip(self):
        queue = self.MaildirQueue()
        mailid = '1700000000.123'
        msg = self._message()
        queue.insert_message(msg, mailid, 'bob@example.com')
        self.assertEqual(queue.fetch_ids(), [mailid])
        self.assertEqual(len(list((pathlib.Path(self.defaults.PENDING_DIR) / 'new').iterdir())), 1)
        fetched = queue.fetch_message(mailid)
        self.assertEqual(fetched['X-TMDA-Recipient'], 'bob@example.com')
        self.assertIn('Pending message', fetched.get_payload())
        self.assertIsNone(msg.get('X-TMDA-Recipient'))
        queue.delete_message(mailid)
        self.assertFalse(queue.find_message(mailid))


    def test_eight_bit_body_is_not_reencoded(self):
        for queue_class in (self.OriginalQueue, self.MaildirQueue):
            with self.subTest(queue=queue_class.__name__):
                self.defaults.PENDING_DIR = str(
                    pathlib.Path(self.tmp.name) / queue_class.__name__)
                msg = Parser().parsestr(
                    'From: alice@example.com\nSubject: Raw body\n\nA\xffB')
                queue = queue_class()
                queue.insert_message(msg, '1700000000.123', 'bob@example.com')
                if queue_class is self.OriginalQueue:
                    path = pathlib.Path(self.defaults.PENDING_DIR) / '1700000000.123.msg'
                else:
                    path = next((pathlib.Path(self.defaults.PENDING_DIR) / 'new').iterdir())
                data = path.read_bytes()
                self.assertIn(b'A\xffB', data)
                self.assertNotIn(b'A\xc3\xbfB', data)
                fetched = queue.fetch_message('1700000000.123')
                self.assertIn('A\xffB', fetched.get_payload())


    def test_reject_unsafe_message_ids(self):
        for queue_class in (self.OriginalQueue, self.MaildirQueue):
            with self.subTest(queue=queue_class.__name__):
                self.defaults.PENDING_DIR = str(
                    pathlib.Path(self.tmp.name) / queue_class.__name__)
                queue = queue_class()
                queue._create()
                for mailid in ('../outside', '../../outside', '123/456',
                               'not-a-mail-id', '123.456/../outside'):
                    with self.subTest(mailid=mailid):
                        with self.assertRaises(ValueError):
                            queue.fetch_message(mailid)
                        with self.assertRaises(ValueError):
                            queue.delete_message(mailid)
                        with self.assertRaises(ValueError):
                            queue.find_message(mailid)
                        with self.assertRaises(ValueError):
                            queue.insert_message(
                                self._message(), mailid, 'bob@example.com')

    def test_cleanup_preserves_working_directory(self):
        for queue_class in (self.OriginalQueue, self.MaildirQueue):
            with self.subTest(queue=queue_class.__name__):
                self.defaults.PENDING_DIR = str(
                    pathlib.Path(self.tmp.name) / queue_class.__name__)
                queue = queue_class()
                queue._create()
                cwd = os.getcwd()
                queue.cleanup()
                self.assertEqual(os.getcwd(), cwd)

    def test_maildir_missing_id_reports_requested_id(self):
        queue = self.MaildirQueue()
        queue._create()
        with self.assertRaisesRegex(IOError, '1700000000.123'):
            queue.fetch_message('1700000000.123')

    def test_maildir_exact_id_matching(self):
        queue = self.MaildirQueue()
        queue.insert_message(self._message(), '1700000000.1234', 'bob@example.com')
        with self.assertRaises(IOError):
            queue.fetch_message('1700000000.123')
        queue.delete_message('1700000000.123')
        self.assertTrue(queue.find_message('1700000000.1234'))


if __name__ == '__main__':
    unittest.main()
