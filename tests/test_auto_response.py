"""Regression coverage for legacy TMDA automatic replies.

Outbound messages are captured; the test never contacts a mail server.
"""
import importlib
import sys
import types
import unittest
from email import message_from_string
from unittest.mock import patch


class AutomaticResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import TMDA
        cls.old_defaults = getattr(TMDA, "Defaults", None)
        cls.old_auto_response = getattr(TMDA, "AutoResponse", None)
        cls.old_module = sys.modules.get("TMDA.AutoResponse")
        defaults = types.ModuleType("TMDA.Defaults")
        defaults.AUTORESPONSE_INCLUDE_SENDER_COPY = 0
        defaults.CONFIRM_MAX_MESSAGE_SIZE = 0
        defaults.TEMPLATE_EMAIL_HEADERS = ("From", "To", "Reply-To")
        defaults.TEMPLATE_ENCODED_HEADERS = ("Subject",)
        defaults.ADDED_HEADERS_SERVER = {}
        defaults.PURGED_HEADERS_SERVER = ()
        defaults.BOUNCE_ENV_SENDER = "<>"
        defaults.PID = 123
        cls.module_patch = patch.dict(sys.modules, {"TMDA.Defaults": defaults})
        cls.module_patch.start()
        TMDA.Defaults = defaults
        sys.modules.pop("TMDA.AutoResponse", None)
        cls.module = importlib.import_module("TMDA.AutoResponse")
        cls.defaults = defaults

    @classmethod
    def tearDownClass(cls):
        import TMDA
        sys.modules.pop("TMDA.AutoResponse", None)
        if cls.old_module is not None:
            sys.modules["TMDA.AutoResponse"] = cls.old_module
        cls.module_patch.stop()
        if cls.old_defaults is None:
            if hasattr(TMDA, "Defaults"):
                delattr(TMDA, "Defaults")
        else:
            TMDA.Defaults = cls.old_defaults
        if cls.old_auto_response is None:
            if hasattr(TMDA, "AutoResponse"):
                delattr(TMDA, "AutoResponse")
        else:
            TMDA.AutoResponse = cls.old_auto_response

    def make_response(self, copy_mode, response_type="request"):
        self.defaults.AUTORESPONSE_INCLUDE_SENDER_COPY = copy_mode
        original = message_from_string(
            "From: sender@example.org\n"
            "To: user@example.org\n"
            "Message-ID: <old@example.org>\n"
            "Subject: original\n\n"
            "original body\n"
        )
        template = (
            "From: user@example.org\n"
            "Subject: Please confirm\n\n"
            "Please reply to confirm.\n"
        )
        response = self.module.AutoResponse(
            original, template, response_type, "sender@example.org")
        response.create()
        return response

    def test_plain_confirmation_keeps_original_headers(self):
        response = self.make_response(0)
        msg = response.mimemsg
        self.assertEqual(msg["To"], "sender@example.org")
        self.assertEqual(msg["Auto-Submitted"], "auto-replied")
        self.assertEqual(msg["In-Reply-To"], "<old@example.org>")
        self.assertEqual(msg.get_content_type(), "text/plain")
        self.assertIn("Date", msg)
        self.assertIn("Message-ID", msg)

    def test_headers_only_confirmation_keeps_mime_attachment(self):
        response = self.make_response(1)
        parts = response.mimemsg.get_payload()
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[1].get_content_type(), "text/rfc822-headers")

    def test_original_message_copy_is_preserved(self):
        response = self.make_response(2)
        parts = response.mimemsg.get_payload()
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[1].get_content_type(), "message/rfc822")

    def test_bounce_has_original_auto_submitted_header(self):
        response = self.make_response(0, "bounce")
        self.assertEqual(response.mimemsg["Auto-Submitted"],
                         "auto-generated (failure)")

    def test_send_preserves_reply_recipient_and_null_sender(self):
        from TMDA import Util
        response = self.make_response(0)
        with patch.object(Util, "sendmail") as sender:
            response.send()
        self.assertEqual(sender.call_args.args[1:],
                         ("sender@example.org", "<>"))


if __name__ == "__main__":
    unittest.main()
