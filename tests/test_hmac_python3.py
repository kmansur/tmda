"""Regression tests for TMDA's legacy HMAC-SHA1 wire format.

Run with: python3 -m unittest discover -s tests -p 'test_hmac_python3.py'
"""
import hashlib
import hmac
import unittest

from TMDA import HMAC


class HMACPython3CompatibilityTests(unittest.TestCase):
    def test_sha1_digest_matches_standard_hmac(self):
        key = b"legacy-key"
        payload = b"message data"
        expected = hmac.new(key, payload, hashlib.sha1).digest()
        self.assertEqual(HMAC.new(key, payload).digest(), expected)

    def test_incremental_updates_match_single_message(self):
        key = "legacy-key"
        expected = hmac.new(b"legacy-key", b"one-two", hashlib.sha1).digest()
        context = HMAC.hmac(key)
        context.update("one-")
        context.update(b"two")
        self.assertEqual(context.digest(), expected)

    def test_latin1_preserves_legacy_python2_byte_values(self):
        key = "\u00e7"
        payload = "\u00e1"
        expected = hmac.new(b"\xe7", b"\xe1", hashlib.sha1).digest()
        self.assertEqual(HMAC.new(key, payload).digest(), expected)

    def test_copy_constructor_does_not_mutate_original(self):
        original = HMAC.hmac(b"key")
        original.update(b"prefix")
        copied = HMAC.hmac(original)
        copied.update(b"-suffix")
        self.assertEqual(
            original.digest(),
            hmac.new(b"key", b"prefix", hashlib.sha1).digest(),
        )
        self.assertEqual(
            copied.digest(),
            hmac.new(b"key", b"prefix-suffix", hashlib.sha1).digest(),
        )


if __name__ == "__main__":
    unittest.main()
