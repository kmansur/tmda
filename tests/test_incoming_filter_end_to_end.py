"""End-to-end incoming TMDA filter regression tests.

A disposable TMDA home and filter file are used; no external mail
delivery or live configuration is involved.
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
FILTER = ROOT / "bin" / "tmda-filter"


class IncomingFilterEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = pathlib.Path(self.temp.name)
        self.tmda = self.home / ".tmda"
        self.tmda.mkdir()
        key = self.tmda / "crypt_key"
        key.write_text("0123456789abcdef" * 3, encoding="ascii")
        key.chmod(0o600)
        self.incoming = self.tmda / "incoming"
        self.incoming.write_text("from sender@example.org accept\n",
                            encoding="ascii")
        config = self.tmda / "config"
        config.write_text(
            "MAIL_TRANSFER_AGENT = 'postfix'\n"
            "DELIVERY = '_filter_'\n"
            "FILTER_INCOMING = " + repr(str(self.incoming)) + "\n"
            "PENDING_CLEANUP_ODDS = 0\n"
            "USERNAME = 'user'\n"
            "HOSTNAME = 'example.org'\n",
            encoding="ascii",
        )
        self.config = config

    def run_filter(self, message):
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["GLOBAL_TMDARC"] = str(self.home / "missing-global")
        env["TMDARC"] = str(self.config)
        env["SENDER"] = "sender@example.org"
        env["RECIPIENT"] = "user@example.org"
        env["EXTENSION"] = ""
        return subprocess.run(
            [sys.executable, str(FILTER), "-p"],
            cwd=ROOT, env=env,
            input=message,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )

    def test_filter_outputs_original_eight_bit_body_octets(self):
        message = (
            b"Return-Path: <sender@example.org>\n"
            b"From: sender@example.org\n"
            b"To: user@example.org\n"
            b"Subject: historical\n\n"
            b"raw\xffpayload\n"
        )
        result = self.run_filter(message)
        self.assertEqual(result.returncode, 0,
                         result.stderr.decode(errors="replace"))
        self.assertIn(b"raw\xffpayload\n", result.stdout)
        self.assertNotIn(b"raw\xc3\xbfpayload", result.stdout)


    def test_filter_hold_queues_original_eight_bit_message(self):
        self.incoming.write_text("from sender@example.org hold\n",
                                 encoding="ascii")
        message = (
            b"From: sender@example.org\n"
            b"To: user@example.org\n"
            b"Subject: held\n\n"
            b"held\xffbody\n"
        )
        result = self.run_filter(message)
        self.assertEqual(result.returncode, 99,
                         result.stderr.decode(errors="replace"))
        pending_dir = self.tmda / "pending"
        files = list(pending_dir.glob("*.msg"))
        self.assertEqual(len(files), 1)
        contents = files[0].read_bytes()
        self.assertIn(b"held\xffbody\n", contents)
        self.assertIn(b"X-TMDA-Recipient: user@example.org", contents)



    def test_filter_confirmation_queues_message_and_sends_request(self):
        self.incoming.write_text("from sender@example.org confirm\n",
                                 encoding="ascii")
        capture = self.home / "confirmation-request"
        stub = self.home / "fake-sendmail"
        stub.write_text(
            "#!" + sys.executable + "\n"
            "import pathlib, sys\n"
            "pathlib.Path(" + repr(str(capture)) + ").write_bytes("
            "sys.stdin.buffer.read())\n",
            encoding="utf-8",
        )
        stub.chmod(0o700)
        with self.config.open("a", encoding="ascii") as cfg:
            cfg.write("MAIL_TRANSPORT = 'sendmail'\n")
            cfg.write("SENDMAIL_PROGRAM = " + repr(str(stub)) + "\n")
            cfg.write("MAX_AUTORESPONSES_PER_DAY = 0\n")
            cfg.write("AUTORESPONSE_INCLUDE_SENDER_COPY = 0\n")
        result = self.run_filter(
            b"From: sender@example.org\n"
            b"To: user@example.org\n"
            b"Subject: confirm this\n\n"
            b"historical \xff payload\n"
        )
        self.assertEqual(result.returncode, 99,
                         result.stderr.decode(errors="replace"))
        pending_messages = list((self.tmda / "pending").glob("*.msg"))
        self.assertEqual(len(pending_messages), 1)
        self.assertIn(b"historical \xff payload",
                      pending_messages[0].read_bytes())
        request = capture.read_bytes()
        self.assertIn(b"Auto-Submitted: auto-replied", request)
        self.assertIn(b"To: sender@example.org", request)



if __name__ == "__main__":
    unittest.main()
