"""Run tmda-pending in a disposable Python 3 environment.

Exercises legacy on-disk pending files, CLI listing and deletion without
contacting a mail transport.
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PENDING = ROOT / "bin" / "tmda-pending"


class PendingCommandEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = pathlib.Path(self.temp.name)
        tmda = self.home / ".tmda"
        tmda.mkdir()
        key = tmda / "crypt_key"
        key.write_text("0123456789abcdef" * 3, encoding="ascii")
        key.chmod(0o600)
        self.pending = tmda / "pending"
        self.pending.mkdir()
        self.message_id = "1700000000.321"
        self.file = self.pending / (self.message_id + ".msg")
        self.file.write_bytes(
            b"Return-Path: <sender@example.org>\n"
            b"From: sender@example.org\n"
            b"To: user@example.org\n"
            b"X-Primary-Address: user@example.org\n"
            b"X-TMDA-Recipient: user@example.org\n"
            b"Subject: old pending\n\n"
            b"legacy \xff body\n"
        )
        self.config = tmda / "config"
        self.config.write_text(
            "MAIL_TRANSFER_AGENT = 'postfix'\n"
            "DELIVERY = '_filter_'\n"
            "PENDING_QUEUE_FORMAT = 'original'\n"
            "PENDING_DIR = " + repr(str(self.pending)) + "\n"
            "USERNAME = 'user'\n"
            "HOSTNAME = 'example.org'\n",
            encoding="ascii",
        )

    def run_command(self, *args):
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["GLOBAL_TMDARC"] = str(self.home / "missing-global")
        env["TMDARC"] = str(self.config)
        return subprocess.run(
            [sys.executable, str(PENDING), *args],
            cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
        )

    def test_batch_terse_listing_reads_legacy_pending_message(self):
        result = self.run_command("-b", "-T", self.message_id)
        self.assertEqual(result.returncode, 0,
                         result.stderr.decode(errors="replace"))
        self.assertIn(self.message_id.encode("ascii"), result.stdout)
        self.assertTrue(self.file.exists())

    def test_batch_delete_removes_original_queue_message(self):
        result = self.run_command("-b", "-d", self.message_id)
        self.assertEqual(result.returncode, 0,
                         result.stderr.decode(errors="replace"))
        self.assertFalse(self.file.exists())


if __name__ == "__main__":
    unittest.main()
