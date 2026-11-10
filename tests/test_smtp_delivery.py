"""Regression coverage for the Python 3 SMTP delivery adapter.

No mail is sent: the SMTP client is replaced with an in-process mock.
"""
import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class SMTPDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # SMTP tests must not depend on ~/.tmda/crypt_key.
        import TMDA
        cls.saved_defaults = getattr(TMDA, "Defaults", None)
        cls.saved_smtp = getattr(TMDA, "SMTP", None)
        defaults = types.ModuleType("TMDA.Defaults")
        for key, value in {
            "SMTPHOST": "localhost",
            "SMTPSSL": False,
            "SMTPSSL_KEYFILE": None,
            "SMTPSSL_CERTFILE": None,
            "SMTPAUTH_USERNAME": "",
            "SMTPAUTH_PASSWORD": "",
            "SMTP_MAX_SESSIONS_PER_CONNECTION": 2,
        }.items():
            setattr(defaults, key, value)
        cls.module_patch = patch.dict(sys.modules, {"TMDA.Defaults": defaults})
        cls.module_patch.start()
        TMDA.Defaults = defaults
        sys.modules.pop("TMDA.SMTP", None)
        cls.SMTP = importlib.import_module("TMDA.SMTP")

    @classmethod
    def tearDownClass(cls):
        import TMDA
        sys.modules.pop("TMDA.SMTP", None)
        if cls.saved_smtp is None:
            if hasattr(TMDA, "SMTP"):
                delattr(TMDA, "SMTP")
        else:
            TMDA.SMTP = cls.saved_smtp
        if cls.saved_defaults is None:
            if hasattr(TMDA, "Defaults"):
                delattr(TMDA, "Defaults")
        else:
            TMDA.Defaults = cls.saved_defaults
        cls.module_patch.stop()

    def setUp(self):
        self.SMTP = self.__class__.SMTP

    def test_sendmail_preserves_envelope_and_message_bytes(self):
        client = MagicMock()
        client.sendmail.return_value = {}
        with patch.object(self.SMTP.smtplib, "SMTP", return_value=client), \
             patch.object(self.SMTP.Defaults, "SMTPHOST", "localhost"), \
             patch.object(self.SMTP.Defaults, "SMTPSSL", False), \
             patch.object(self.SMTP.Defaults, "SMTPAUTH_USERNAME", ""), \
             patch.object(self.SMTP.Defaults, "SMTPAUTH_PASSWORD", ""), \
             patch.object(self.SMTP.Defaults, "SMTP_MAX_SESSIONS_PER_CONNECTION", 2):
            connection = self.SMTP.Connection()
            payload = b"Subject: legacy\r\n\r\n\xe7\r\n"
            self.assertEqual(
                connection.sendmail("sender@example.org", ["recipient@example.org"], payload),
                {},
            )
            client.sendmail.assert_called_once_with(
                "sender@example.org", ["recipient@example.org"], payload
            )
            self.assertEqual(connection.sendmail("sender@example.org", [], b"test"), {})
            client.quit.assert_called_once()

    def test_sendmail_encodes_legacy_eight_bit_text_without_data_loss(self):
        client = MagicMock()
        client.sendmail.return_value = {}
        with patch.object(self.SMTP.smtplib, "SMTP", return_value=client), \
             patch.object(self.SMTP.Defaults, "SMTPHOST", "localhost"), \
             patch.object(self.SMTP.Defaults, "SMTPSSL", False), \
             patch.object(self.SMTP.Defaults, "SMTPAUTH_USERNAME", ""), \
             patch.object(self.SMTP.Defaults, "SMTPAUTH_PASSWORD", ""), \
             patch.object(self.SMTP.Defaults, "SMTP_MAX_SESSIONS_PER_CONNECTION", 1):
            self.SMTP.Connection().sendmail(
                "from@example.org", ["to@example.org"],
                "Subject: legacy\r\n\r\ncaf\u00e9\r\n",
            )
            client.sendmail.assert_called_once_with(
                "from@example.org", ["to@example.org"],
                b"Subject: legacy\r\n\r\ncaf\xe9\r\n",
            )

    def test_starttls_and_authentication_keep_existing_order(self):
        client = MagicMock()
        with patch.object(self.SMTP.smtplib, "SMTP", return_value=client), \
             patch.object(self.SMTP.Defaults, "SMTPHOST", "localhost"), \
             patch.object(self.SMTP.Defaults, "SMTPSSL", True), \
             patch.object(self.SMTP.Defaults, "SMTPSSL_KEYFILE", None), \
             patch.object(self.SMTP.Defaults, "SMTPSSL_CERTFILE", None), \
             patch.object(self.SMTP.Defaults, "SMTPAUTH_USERNAME", "user"), \
             patch.object(self.SMTP.Defaults, "SMTPAUTH_PASSWORD", "secret"), \
             patch.object(self.SMTP.Defaults, "SMTP_MAX_SESSIONS_PER_CONNECTION", 1):
            self.SMTP.Connection().sendmail("sender@example.org", ["to@example.org"], b"hello")
            self.assertEqual(client.starttls.call_count, 1)
            self.assertEqual(client.ehlo.call_count, 1)
            client.login.assert_called_once_with("user", "secret")
            self.assertLess(
                client.method_calls.index(next(c for c in client.method_calls if c[0] == "starttls")),
                client.method_calls.index(next(c for c in client.method_calls if c[0] == "login")),
            )

    def test_smtp_protocol_exception_discards_connection(self):
        client = MagicMock()
        client.sendmail.side_effect = self.SMTP.smtplib.SMTPException("test")
        with patch.object(self.SMTP.smtplib, "SMTP", return_value=client), \
             patch.object(self.SMTP.Defaults, "SMTPHOST", "localhost"), \
             patch.object(self.SMTP.Defaults, "SMTPSSL", False), \
             patch.object(self.SMTP.Defaults, "SMTPAUTH_USERNAME", ""), \
             patch.object(self.SMTP.Defaults, "SMTPAUTH_PASSWORD", ""), \
             patch.object(self.SMTP.Defaults, "SMTP_MAX_SESSIONS_PER_CONNECTION", 2):
            connection = self.SMTP.Connection()
            with self.assertRaises(self.SMTP.smtplib.SMTPException):
                connection.sendmail("from@example.org", ["to@example.org"], b"test")
            client.quit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
