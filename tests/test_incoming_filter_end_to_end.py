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
        incoming = self.tmda / "incoming"
        incoming.write_text("from sender@example.org accept\n",
                            encoding="ascii")
        config = self.tmda / "config"
        config.write_text(
            "MAIL_TRANSFER_AGENT = 'postfix'\n"
            "DELIVERY = '_filter_'\n"
            "FILTER_INCOMING = " + repr(str(incoming)) + "\n"
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


if __name__ == "__main__":
    unittest.main()
