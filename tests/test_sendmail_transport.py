"""Regression tests for the historic sendmail transport invocation."""
import sys
import types
import unittest
from unittest.mock import patch


class LegacySendmailTransportTests(unittest.TestCase):
    def setUp(self):
        import TMDA
        from TMDA import Util
        self.tmda = TMDA
        self.util = Util
        self.defaults = types.ModuleType("TMDA.Defaults")
        self.defaults.MAIL_TRANSPORT = "sendmail"
        self.defaults.MAIL_TRANSFER_AGENT = "postfix"
        self.defaults.SENDMAIL_PROGRAM = "/usr/sbin/sendmail"
        self.module_patch = patch.dict(sys.modules, {"TMDA.Defaults": self.defaults})
        self.module_patch.start()
        self.previous_defaults = getattr(TMDA, "Defaults", None)
        TMDA.Defaults = self.defaults
        self.addCleanup(self.restore)

    def restore(self):
        self.module_patch.stop()
        if self.previous_defaults is None:
            if hasattr(self.tmda, "Defaults"):
                delattr(self.tmda, "Defaults")
        else:
            self.tmda.Defaults = self.previous_defaults

    def test_postfix_null_envelope_sender_keeps_legacy_empty_argument(self):
        calls = []
        with patch.object(self.util, "pipecmd",
                          side_effect=lambda *args: calls.append(args)):
            self.util.sendmail("Subject: test\n\ncaf\xe9",
                               "recipient@example.org", "<>")
        self.assertEqual(calls, [
            (("/usr/sbin/sendmail", "-i", "-f", "", "--",
              "recipient@example.org"), "Subject: test\n\ncaf\xe9")
        ])

    def test_other_mta_null_envelope_sender_uses_angle_brackets(self):
        self.defaults.MAIL_TRANSFER_AGENT = "sendmail"
        with patch.object(self.util, "pipecmd") as pipe:
            self.util.sendmail("test", "recipient@example.org", "")
        pipe.assert_called_once_with(
            ("/usr/sbin/sendmail", "-i", "-f", "<>", "--",
             "recipient@example.org"), "test"
        )

    def test_explicit_sender_keeps_original_argument_vector(self):
        with patch.object(self.util, "pipecmd") as pipe:
            self.util.sendmail("message", "target@example.org",
                               "sender@example.org")
        pipe.assert_called_once_with(
            ("/usr/sbin/sendmail", "-i", "-f", "sender@example.org",
             "--", "target@example.org"), "message"
        )


if __name__ == "__main__":
    unittest.main()
