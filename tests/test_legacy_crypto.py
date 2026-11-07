# -*- python -*-
#
# Copyright (C) 2001-2007 Jason R. Mastaler <jason@mastaler.com>
#
# This file is part of TMDA.
#
# TMDA is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.  A copy of this license should
# be included in the file COPYING.

"""Regression tests for legacy TMDA HMAC and cookie formats."""

import base64
import hashlib
import hmac
import importlib
import sys
import types
import unittest
from unittest.mock import patch


KEY = bytes(range(20))
HMAC_BYTES = 3


def legacy_hex(message):
    return hmac.new(KEY, message.encode('latin-1'), hashlib.sha1).digest()[:HMAC_BYTES].hex()


class HMACTests(unittest.TestCase):
    def test_rfc_2202_sha1_vector(self):
        from TMDA import HMAC
        digest = HMAC.new(b'\x0b' * 20, 'Hi There').digest()
        self.assertEqual(digest.hex(), 'b617318655057264e28bc0b6fb378c8ef146be00')

    def test_incremental_and_copy(self):
        from TMDA import HMAC
        original = HMAC.new(KEY)
        original.update('first')
        copied = HMAC.hmac(original)
        original.update('second')
        copied.update('second')
        expected = hmac.new(KEY, b'firstsecond', hashlib.sha1).digest()
        self.assertEqual(original.digest(), expected)
        self.assertEqual(copied.digest(), expected)

    def test_eight_bit_python2_string_compatibility(self):
        from TMDA import HMAC
        self.assertEqual(
            HMAC.new(KEY, 'caf\xe9').digest(),
            hmac.new(KEY, b'caf\xe9', hashlib.sha1).digest(),
        )


class CookieTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        defaults = types.ModuleType('TMDA.Defaults')
        defaults.CRYPT_KEY = KEY
        defaults.HMAC_BYTES = HMAC_BYTES
        defaults.DATED_TIMEOUT = '7d'
        defaults.RECIPIENT_DELIMITER = '-'
        defaults.TAGS_CONFIRM = ['confirm']
        defaults.TAGS_DATED = ['dated']
        defaults.TAGS_SENDER = ['sender']
        defaults.TAGS_KEYWORD = ['keyword']
        defaults.CONFIRM_ADDRESS = None

        util = types.ModuleType('TMDA.Util')
        util.seconds = lambda timeout: 7 * 86400 if timeout == '7d' else 0

        cls.modules = patch.dict(sys.modules, {
            'TMDA.Defaults': defaults,
            'TMDA.Util': util,
        })
        cls.modules.start()
        import TMDA
        cls.saved_defaults = getattr(TMDA, 'Defaults', None)
        cls.saved_util = getattr(TMDA, 'Util', None)
        TMDA.Defaults = defaults
        TMDA.Util = util
        sys.modules.pop('TMDA.Cookie', None)
        cls.cookie = importlib.import_module('TMDA.Cookie')

    @classmethod
    def tearDownClass(cls):
        import TMDA
        sys.modules.pop('TMDA.Cookie', None)
        if cls.saved_defaults is None:
            delattr(TMDA, 'Defaults')
        else:
            TMDA.Defaults = cls.saved_defaults
        if cls.saved_util is None:
            delattr(TMDA, 'Util')
        else:
            TMDA.Util = cls.saved_util
        cls.modules.stop()

    def test_confirmation_cookie(self):
        timestamp, pid = '1700000000', '123'
        mac = legacy_hex((timestamp + pid + 'accept'))
        self.assertEqual(
            self.cookie.make_confirm_cookie(timestamp, pid, 'accept'),
            timestamp + '.' + pid + '.' + mac,
        )

    def test_dated_cookie(self):
        timestamp = str(1700000000 + 7 * 86400)
        self.assertEqual(
            self.cookie.make_dated_cookie(1700000000, '7d'),
            timestamp + '.' + legacy_hex(timestamp),
        )

    def test_sender_cookie(self):
        self.assertEqual(
            self.cookie.make_sender_cookie('Alice@Example.COM'),
            legacy_hex('alice@example.com'),
        )

    def test_keyword_cookie(self):
        self.assertEqual(
            self.cookie.make_keyword_cookie('news-letter'),
            'news?letter.' + legacy_hex('news?letter'),
        )

    def test_keyword_sanitization(self):
        self.assertEqual(
            self.cookie.make_keyword_cookie('news letter'),
            'news?letter.' + legacy_hex('news?letter'),
        )

    def test_fingerprint(self):
        headers = ['From: alice@example.com\r\n', 'Subject: hello\r\n']
        expected = base64.b64encode(
            hmac.new(KEY, ''.join(headers).encode('latin-1'), hashlib.sha1).digest()
        ).decode('ascii').rstrip('=')
        self.assertEqual(self.cookie.make_fingerprint(headers), expected)


if __name__ == '__main__':
    unittest.main()
