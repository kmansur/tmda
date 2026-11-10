"""Legacy pending queue format regression tests for Python 3.

The real user configuration is intentionally not loaded.  These tests
exercise the on-disk original and Maildir queue formats in temporary dirs.
"""
import importlib
import os
import sys
import tempfile
import types
import unittest
from email.message import Message
from unittest.mock import patch


class PendingQueueFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import TMDA
        cls.previous_defaults = getattr(TMDA, "Defaults", None)
        cls.previous_util = getattr(TMDA, "Util", None)
        cls.previous_queue = {
            name: sys.modules.get(name)
            for name in (
                "TMDA.Queue.Queue",
                "TMDA.Queue.OriginalQueue",
                "TMDA.Queue.MaildirQueue",
            )
        }
        defaults = types.ModuleType("TMDA.Defaults")
        defaults.PENDING_DIR = ""
        defaults.PENDING_DELETE_APPEND = None
        defaults.PENDING_LIFETIME = "7d"
        cls.module_patch = patch.dict(sys.modules, {"TMDA.Defaults": defaults})
        cls.module_patch.start()
        TMDA.Defaults = defaults
        for name in cls.previous_queue:
            sys.modules.pop(name, None)
        cls.original_module = importlib.import_module("TMDA.Queue.OriginalQueue")
        cls.maildir_module = importlib.import_module("TMDA.Queue.MaildirQueue")
        cls.defaults = defaults

    @classmethod
    def tearDownClass(cls):
        import TMDA
        for name in cls.previous_queue:
            sys.modules.pop(name, None)
            if cls.previous_queue[name] is not None:
                sys.modules[name] = cls.previous_queue[name]
        cls.module_patch.stop()
        if cls.previous_defaults is None:
            if hasattr(TMDA, "Defaults"):
                delattr(TMDA, "Defaults")
        else:
            TMDA.Defaults = cls.previous_defaults
        if cls.previous_util is None:
            if hasattr(TMDA, "Util"):
                delattr(TMDA, "Util")
        else:
            TMDA.Util = cls.previous_util

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.defaults.PENDING_DIR = self.temp.name

    @staticmethod
    def message():
        msg = Message()
        msg["From"] = "sender@example.org"
        msg["Subject"] = "legacy"
        msg["X-TMDA-Recipient"] = "prior@example.org"
        msg.set_payload("caf\xe9\n")
        return msg

    def test_original_queue_preserves_legacy_bytes_and_headers(self):
        queue = self.original_module.OriginalQueue()
        message = self.message()
        queue.insert_message(message, "1700000000.321", "target@example.org")
        self.assertEqual(message.get_all("X-TMDA-Recipient"), ["prior@example.org"])
        self.assertEqual(queue.fetch_ids(), ["1700000000.321"])
        with open(os.path.join(self.temp.name, "1700000000.321.msg"), "rb") as stream:
            raw = stream.read()
        self.assertIn(b"caf\xe9\n", raw)
        fetched = queue.fetch_message("1700000000.321", fullParse=True)
        self.assertEqual(fetched["X-TMDA-Recipient"], "target@example.org")
        self.assertIn("caf\xe9", fetched.get_payload())
        queue.delete_message("1700000000.321")
        self.assertFalse(queue.find_message("1700000000.321"))

    def test_maildir_queue_preserves_legacy_bytes_and_headers(self):
        queue = self.maildir_module.MaildirQueue()
        message = self.message()
        queue.insert_message(message, "1700000000.322", "target@example.org")
        self.assertEqual(message.get_all("X-TMDA-Recipient"), ["prior@example.org"])
        self.assertEqual(queue.fetch_ids(), ["1700000000.322"])
        new_files = os.listdir(os.path.join(self.temp.name, "new"))
        self.assertEqual(len(new_files), 1)
        with open(os.path.join(self.temp.name, "new", new_files[0]), "rb") as stream:
            self.assertIn(b"caf\xe9\n", stream.read())
        fetched = queue.fetch_message("1700000000.322", fullParse=True)
        self.assertEqual(fetched["X-TMDA-Recipient"], "target@example.org")
        queue.delete_message("1700000000.322")
        self.assertFalse(queue.fetch_ids())

    def test_original_queue_does_not_overwrite_existing_id(self):
        queue = self.original_module.OriginalQueue()
        queue.insert_message(self.message(), "1700000000.323", "a@example.org")
        with open(os.path.join(self.temp.name, "1700000000.323.msg"), "rb") as fp:
            original = fp.read()
        with self.assertRaises(FileExistsError):
            queue.insert_message(self.message(), "1700000000.323", "b@example.org")
        with open(os.path.join(self.temp.name, "1700000000.323.msg"), "rb") as fp:
            self.assertEqual(fp.read(), original)

    def test_rejects_malformed_queue_ids_before_filesystem_access(self):
        for queue in (self.original_module.OriginalQueue(),
                      self.maildir_module.MaildirQueue()):
            for bad_id in ("../passwd", "1700000000.1/../x", "garbage"):
                with self.subTest(queue=queue.format, mailid=bad_id):
                    with self.assertRaises(ValueError):
                        queue.insert_message(self.message(), bad_id, "a@example.org")


if __name__ == "__main__":
    unittest.main()
