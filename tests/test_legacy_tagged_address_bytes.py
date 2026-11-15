"""Verify tagged sender addresses retain Python 2 byte-case semantics."""
import hashlib
import hmac
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CRYPT_KEY = bytes.fromhex("00112233445566778899aabbccddeeff00112233")


class LegacyTaggedAddressTests(unittest.TestCase):
    def run_script(self, source):
        with tempfile.TemporaryDirectory() as home:
            folder = pathlib.Path(home) / ".tmda"
            folder.mkdir()
            keyfile = folder / "crypt_key"
            keyfile.write_text(CRYPT_KEY.hex(), encoding="ascii")
            keyfile.chmod(0o600)
            config = folder / "config"
            config.write_text(
                "USERNAME = 'alice'\nHOSTNAME = 'example.org'\n",
                encoding="ascii",
            )
            env = os.environ.copy()
            env.update({
                "HOME": home,
                "TMDARC": str(config),
                "GLOBAL_TMDARC": str(folder / "nonexistent-global"),
            })
            return subprocess.run(
                [sys.executable, "-c", source], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=10,
            )

    def test_sender_cookie_and_address_round_trip_with_high_bit_bytes(self):
        script = (
            "from TMDA import Address, Cookie\n"
            "sender = 'BOB@EX\\xc9MPLE.ORG'\n"
            "base = 'ALICE@EX\\xc9MPLE.ORG'\n"
            "created = Address.SenderAddress().create(base, sender)\n"
            "print(str(created))\n"
            "Address.SenderAddress(str(created)).verify(sender)\n"
            "Address.SenderAddress(str(created)).verify('bob@ex\\xc9mple.org')\n"
            "print(Cookie.make_sender_cookie(sender))\n"
        )
        result = self.run_script(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = hmac.new(CRYPT_KEY, b"bob@ex\xc9mple.org", hashlib.sha1)
        hex_mac = expected.digest()[:3].hex()
        output = result.stdout.splitlines()
        self.assertIn(hex_mac, output[0])
        self.assertEqual(output[0], "alice-sender-" + hex_mac + "@ex\xc9mple.org")
        self.assertEqual(output[1], hex_mac)


if __name__ == "__main__":
    unittest.main()
