"""Regression coverage for the Python 3 SMTP delivery adapter.

No mail is sent: the SMTP client is replaced with an in-process mock.
"""
import unittest
from unittest.mock import MagicMock, patch

from TMDA import SMTP


class SMTPDeliveryTests(unittest.TestCase):
    def test_sendmail_preserves_envelope_and_message_bytes(self):
        client = MagicMock()
        client.sendmail.return_value = {}
        with patch.object(SMTP.smtplib, "SMTP", return_value=client), \
             patch.object(SMTP.Defaults, "SMTPHOST", "localhost"), \
             patch.object(SMTP.Defaults, "SMTPSSL", False), \
             patch.object(SMTP.Defaults, "SMTPAUTH_USERNAME", ""), \
             patch.object(SMTP.Defaults, "SMTPAUTH_PASSWORD", ""), \
             patch.object(SMTP.Defaults, "SMTP_MAX_SESSIONS_PER_CONNECTION", 2):
            connection = SMTP.Connection()
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

    def test_starttls_and_authentication_keep_existing_order(self):
        client = MagicMock()
        with patch.object(SMTP.smtplib, "SMTP", return_value=client), \
             patch.object(SMTP.Defaults, "SMTPHOST", "localhost"), \
             patch.object(SMTP.Defaults, "SMTPSSL", True), \
             patch.object(SMTP.Defaults, "SMTPSSL_KEYFILE", None), \
             patch.object(SMTP.Defaults, "SMTPSSL_CERTFILE", None), \
             patch.object(SMTP.Defaults, "SMTPAUTH_USERNAME", "user"), \
             patch.object(SMTP.Defaults, "SMTPAUTH_PASSWORD", "secret"), \
             patch.object(SMTP.Defaults, "SMTP_MAX_SESSIONS_PER_CONNECTION", 1):
            SMTP.Connection().sendmail("sender@example.org", ["to@example.org"], b"hello")
            self.assertEqual(client.starttls.call_count, 1)
            self.assertEqual(client.ehlo.call_count, 1)
            client.login.assert_called_once_with("user", "secret")
            self.assertLess(
                client.method_calls.index(next(c for c in client.method_calls if c[0] == "starttls")),
                client.method_calls.index(next(c for c in client.method_calls if c[0] == "login")),
            )

    def test_smtp_protocol_exception_discards_connection(self):
        client = MagicMock()
        client.sendmail.side_effect = SMTP.smtplib.SMTPException("test")
        with patch.object(SMTP.smtplib, "SMTP", return_value=client), \
             patch.object(SMTP.Defaults, "SMTPHOST", "localhost"), \
             patch.object(SMTP.Defaults, "SMTPSSL", False), \
             patch.object(SMTP.Defaults, "SMTPAUTH_USERNAME", ""), \
             patch.object(SMTP.Defaults, "SMTPAUTH_PASSWORD", ""), \
             patch.object(SMTP.Defaults, "SMTP_MAX_SESSIONS_PER_CONNECTION", 2):
            connection = SMTP.Connection()
            with self.assertRaises(SMTP.smtplib.SMTPException):
                connection.sendmail("from@example.org", ["to@example.org"], b"test")
            client.quit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
