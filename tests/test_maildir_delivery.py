"""Regression coverage for standard Maildir deliveries in Python 3."""
import importlib
import os
import signal
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class MaildirDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import TMDA
        cls.old_defaults = getattr(TMDA, "Defaults", None)
        cls.old_deliver = getattr(TMDA, "Deliver", None)
        cls.old_module = sys.modules.get("TMDA.Deliver")
        defaults = types.ModuleType("TMDA.Defaults")
        cls.module_patch = patch.dict(sys.modules, {"TMDA.Defaults": defaults})
        cls.module_patch.start()
        TMDA.Defaults = defaults
        sys.modules.pop("TMDA.Deliver", None)
        cls.module = importlib.import_module("TMDA.Deliver")

    @classmethod
    def tearDownClass(cls):
        import TMDA
        sys.modules.pop("TMDA.Deliver", None)
        if cls.old_module is not None:
            sys.modules["TMDA.Deliver"] = cls.old_module
        cls.module_patch.stop()
        if cls.old_defaults is None:
            if hasattr(TMDA, "Defaults"):
                delattr(TMDA, "Defaults")
        else:
            TMDA.Defaults = cls.old_defaults
        if cls.old_deliver is None:
            if hasattr(TMDA, "Deliver"):
                delattr(TMDA, "Deliver")
        else:
            TMDA.Deliver = cls.old_deliver

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.maildir = self.temp.name
        for dirname in ("tmp", "new", "cur"):
            os.mkdir(os.path.join(self.maildir, dirname))
        self.delivery = self.module.Deliver(None, "unused")

    def deliver(self, message):
        # Do not change the process's SIGALRM handler or timer during CI.
        with patch.object(self.module.signal, "signal"), \
             patch.object(self.module.signal, "alarm"):
            self.delivery._Deliver__deliver_maildir(message, self.maildir)

    def test_maildir_preserves_original_eight_bit_message(self):
        self.deliver("Subject: legacy\n\ncaf\xe9\n")
        entries = os.listdir(os.path.join(self.maildir, "new"))
        self.assertEqual(len(entries), 1)
        with open(os.path.join(self.maildir, "new", entries[0]), "rb") as fp:
            self.assertEqual(fp.read(), b"Subject: legacy\n\ncaf\xe9\n")
        self.assertFalse(os.listdir(os.path.join(self.maildir, "tmp")))

    def test_maildir_accepts_raw_bytes_without_transcoding(self):
        self.deliver(b"Subject: binary\n\n\x00\x80\xff\n")
        entries = os.listdir(os.path.join(self.maildir, "new"))
        with open(os.path.join(self.maildir, "new", entries[0]), "rb") as fp:
            self.assertEqual(fp.read(), b"Subject: binary\n\n\x00\x80\xff\n")
        self.assertFalse(os.listdir(os.path.join(self.maildir, "tmp")))

    def test_invalid_maildir_rejects_delivery(self):
        os.rmdir(os.path.join(self.maildir, "cur"))
        with self.assertRaises(self.module.Errors.DeliveryError):
            self.deliver(b"Subject: test\n\nbody\n")
        self.assertFalse(os.listdir(os.path.join(self.maildir, "new")))


if __name__ == "__main__":
    unittest.main()
