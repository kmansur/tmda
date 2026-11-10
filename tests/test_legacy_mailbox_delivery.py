"""Regression coverage for TMDA's legacy mbox and MMDF delivery.

No MTA is contacted and all files are created in a temporary directory.
"""
import importlib
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from email.message import Message


class LegacyMailboxDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import TMDA
        cls.saved_defaults = getattr(TMDA, "Defaults", None)
        cls.saved_deliver = getattr(TMDA, "Deliver", None)
        cls.saved_module = sys.modules.get("TMDA.Deliver")
        defaults = types.ModuleType("TMDA.Defaults")
        cls.module_patch = patch.dict(sys.modules, {"TMDA.Defaults": defaults})
        cls.module_patch.start()
        TMDA.Defaults = defaults
        sys.modules.pop("TMDA.Deliver", None)
        cls.delivery_module = importlib.import_module("TMDA.Deliver")

    @classmethod
    def tearDownClass(cls):
        import TMDA
        sys.modules.pop("TMDA.Deliver", None)
        if cls.saved_module is not None:
            sys.modules["TMDA.Deliver"] = cls.saved_module
        cls.module_patch.stop()
        if cls.saved_deliver is None:
            if hasattr(TMDA, "Deliver"):
                delattr(TMDA, "Deliver")
        else:
            TMDA.Deliver = cls.saved_deliver
        if cls.saved_defaults is None:
            if hasattr(TMDA, "Defaults"):
                delattr(TMDA, "Defaults")
        else:
            TMDA.Defaults = cls.saved_defaults

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.message = Message()
        self.delivery = self.delivery_module.Deliver(self.message, "unused")

    def pathname(self, filename):
        return os.path.join(self.temp.name, filename)

    def test_mbox_keeps_original_eight_bit_octets(self):
        path = self.pathname("mailbox")
        with open(path, "wb") as output:
            output.write(b"")
        self.delivery._Deliver__deliver_mbox("From sender\ncaf\xe9", path)
        with open(path, "rb") as stream:
            self.assertEqual(stream.read(), b"From sender\ncaf\xe9\n\n")

    def test_mbox_appends_without_erasing_existing_mail(self):
        path = self.pathname("mailbox")
        original = b"From prior@example.org\nSubject: old\n\nold\n\n"
        with open(path, "wb") as stream:
            stream.write(original)
        self.delivery._Deliver__deliver_mbox(b"From sender\nnew\n", path)
        with open(path, "rb") as stream:
            self.assertEqual(stream.read(), original + b"From sender\nnew\n\n")

    def test_mbox_rejects_wrong_existing_format(self):
        path = self.pathname("mailbox")
        original = b"Not an mbox\n"
        with open(path, "wb") as stream:
            stream.write(original)
        with self.assertRaises(self.delivery_module.Errors.DeliveryError):
            self.delivery._Deliver__deliver_mbox(b"From sender\nnew", path)
        with open(path, "rb") as stream:
            self.assertEqual(stream.read(), original)

    def test_mmdf_preserves_delimiters_and_eight_bit_octets(self):
        path = self.pathname("mailbox.mmdf")
        with open(path, "wb") as stream:
            stream.write(b"")
        self.delivery._Deliver__deliver_mmdf("Subject: old\n\ncaf\xe9", path)
        with open(path, "rb") as stream:
            self.assertEqual(stream.read(),
                b"\x01\x01\x01\x01\nSubject: old\n\ncaf\xe9\n\n\x01\x01\x01\x01\n")

    def test_mmdf_rejects_wrong_existing_format(self):
        path = self.pathname("mailbox.mmdf")
        original = b"Not MMDF\n"
        with open(path, "wb") as stream:
            stream.write(original)
        with self.assertRaises(self.delivery_module.Errors.DeliveryError):
            self.delivery._Deliver__deliver_mmdf(b"message\n", path)
        with open(path, "rb") as stream:
            self.assertEqual(stream.read(), original)


if __name__ == "__main__":
    unittest.main()
