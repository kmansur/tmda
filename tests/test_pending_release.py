"""Regression tests for releasing legacy TMDA pending messages.

No production MTA is contacted; reinjection is captured in memory.
"""
import importlib
import sys
import types
import unittest
from email.message import Message as EmailMessage
from unittest.mock import patch


class PendingReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import TMDA
        from TMDA import Util
        cls.util = Util
        cls.previous = {
            name: sys.modules.get(name)
            for name in ("TMDA.Defaults", "TMDA.Queue.Queue", "TMDA.Pending",
                         "TMDA.Cookie")
        }
        cls.previous_attrs = {
            name: getattr(TMDA, name, None)
            for name in ("Defaults", "Pending", "Cookie")
        }
        defaults = types.ModuleType("TMDA.Defaults")
        defaults.RECIPIENT_DELIMITER = "-"
        defaults.PRIMARY_ADDRESS_MATCH = 0
        defaults.PENDING_RELEASE_APPEND = None
        defaults.PENDING_DELETE_APPEND = None
        defaults.PENDING_WHITELIST_APPEND = None
        defaults.PENDING_BLACKLIST_APPEND = None

        cls.raw_message = EmailMessage()
        cls.raw_message["Return-Path"] = "<sender@example.org>"
        cls.raw_message["X-Primary-Address"] = "user@example.org"
        cls.raw_message["X-TMDA-Recipient"] = "target@example.org"
        cls.raw_message["Delivered-To"] = "target@example.org"
        cls.raw_message["Subject"] = "historical message"
        cls.raw_message.set_payload("caf\xe9\n")

        class FakeQueue:
            def init(self):
                return self
            def find_message(self, mailid):
                return mailid == "1700000000.321"
            def fetch_message(self, mailid, fullParse=False):
                # Each message has an independent header collection.
                import copy
                return copy.deepcopy(PendingReleaseTests.raw_message)

        queue_module = types.ModuleType("TMDA.Queue.Queue")
        queue_module.Queue = FakeQueue
        cookie_module = types.ModuleType("TMDA.Cookie")
        cookie_module.make_confirm_cookie = (
            lambda timestamp, pid, keyword=None:
            "%s.%s.%s" % (timestamp, pid, keyword)
        )
        cls.module_patch = patch.dict(sys.modules, {
            "TMDA.Defaults": defaults,
            "TMDA.Queue.Queue": queue_module,
            "TMDA.Cookie": cookie_module,
        })
        cls.module_patch.start()
        TMDA.Defaults = defaults
        TMDA.Cookie = cookie_module
        sys.modules.pop("TMDA.Pending", None)
        cls.pending = importlib.import_module("TMDA.Pending")
        cls.defaults = defaults

    @classmethod
    def tearDownClass(cls):
        import TMDA
        for name, previous in cls.previous.items():
            sys.modules.pop(name, None)
            if previous is not None:
                sys.modules[name] = previous
        cls.module_patch.stop()
        for name, previous in cls.previous_attrs.items():
            if previous is None:
                if hasattr(TMDA, name):
                    delattr(TMDA, name)
            else:
                setattr(TMDA, name, previous)

    def test_release_preserves_sender_recipient_and_legacy_body(self):
        pending_message = self.pending.Message("1700000000.321")
        captured = []
        with patch.object(self.util, "sendmail",
                          side_effect=lambda *args: captured.append(args)):
            pending_message.release()
        self.assertEqual(len(captured), 1)
        message, recipient, envelope_sender = captured[0]
        self.assertEqual(recipient, "target@example.org")
        self.assertEqual(envelope_sender, "sender@example.org")
        self.assertIn("caf\xe9", message)
        self.assertIn("X-TMDA-Confirm-Done: 1700000000.321.done", message)
        self.assertIn("Old-Delivered-To: target@example.org", message)
        self.assertNotIn("X-TMDA-Recipient:", message)
        self.assertNotIn("Return-Path:", message)

    def test_explicit_recipient_overrides_pending_header(self):
        pending_message = self.pending.Message(
            "1700000000.321", recipient="override@example.org")
        captured = []
        with patch.object(self.util, "sendmail",
                          side_effect=lambda *args: captured.append(args)):
            pending_message.release()
        self.assertEqual(captured[0][1], "override@example.org")


if __name__ == "__main__":
    unittest.main()
