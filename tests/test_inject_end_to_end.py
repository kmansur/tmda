"""End-to-end Python 3 tests of tmda-inject with an isolated fake sendmail.

The temporary executable only writes captures to disk. No network, real
sendmail process or user configuration is used.
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
INJECT = ROOT / "bin" / "tmda-inject"


class InjectEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = pathlib.Path(self.temp.name)
        self.tmda = self.home / ".tmda"
        self.tmda.mkdir()
        self.key = self.tmda / "crypt_key"
        self.key.write_text("0123456789abcdef" * 3, encoding="ascii")
        self.key.chmod(0o600)
        self.capture = self.home / "captured-message"
        self.arguments = self.home / "captured-arguments"
        self.stub = self.home / "fake-sendmail"
        self.stub.write_text(
            "#!" + sys.executable + "\n"
            "import os, pathlib, sys\n"
            "pathlib.Path(os.environ['TMDA_TEST_CAPTURE']).write_bytes("
            "sys.stdin.buffer.read())\n"
            "pathlib.Path(os.environ['TMDA_TEST_ARGS']).write_text("
            "'\\n'.join(sys.argv[1:]), encoding='utf-8')\n",
            encoding="utf-8",
        )
        self.stub.chmod(0o700)
        self.config = self.tmda / "config"
        self.config.write_text(
            "MAIL_TRANSFER_AGENT = 'postfix'\n"
            "DELIVERY = '_filter_'\n"
            "MAIL_TRANSPORT = 'sendmail'\n"
            "SENDMAIL_PROGRAM = " + repr(str(self.stub)) + "\n"
            "ACTION_OUTGOING = 'bare'\n"
            "USERNAME = 'user'\n"
            "HOSTNAME = 'example.org'\n"
            "FULLNAME = 'User Example'\n",
            encoding="ascii",
        )

    def run_inject(self, args, content):
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["GLOBAL_TMDARC"] = str(self.home / "missing-global")
        env["TMDARC"] = str(self.config)
        env["TMDA_TEST_CAPTURE"] = str(self.capture)
        env["TMDA_TEST_ARGS"] = str(self.arguments)
        return subprocess.run(
            [sys.executable, str(INJECT)] + args,
            input=content,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )

    def test_inject_delivers_legacy_eight_bit_body_with_envelope(self):
        result = self.run_inject(
            ["target@example.org"],
            b"From: user@example.org\n"
            b"To: target@example.org\n"
            b"Subject: original\n"
            b"X-TMDA: bare\n"
            b"\n"
            b"legacy \xff content\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        message = self.capture.read_bytes()
        self.assertIn(b"legacy \xff content\n", message)
        self.assertNotIn(b"X-TMDA:", message)
        self.assertIn(b"X-Delivery-Agent: TMDA/", message)
        arguments = self.arguments.read_text(encoding="utf-8").splitlines()
        self.assertEqual(arguments,
                         ["-i", "-f", "user@example.org", "--",
                          "target@example.org"])

    def test_qfilter_mode_preserves_exit_code_99(self):
        result = self.run_inject(
            ["-q", "target@example.org"],
            b"From: user@example.org\n"
            b"X-TMDA: bare\n\n"
            b"qfilter content\n",
        )
        self.assertEqual(result.returncode, 99, result.stderr.decode(errors="replace"))
        self.assertIn(b"qfilter content\n", self.capture.read_bytes())


if __name__ == "__main__":
    unittest.main()
