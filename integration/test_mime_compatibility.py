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

"""Preserve wire message data when parsing and serializing MIME messages."""

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
import io
import unittest

from TMDA import Util


class MimeCompatibilityTests(unittest.TestCase):
    @staticmethod
    def _multipart_fixture():
        msg = EmailMessage(policy=policy.SMTP)
        msg['From'] = 'alice@example.com'
        msg['To'] = 'bob@example.com'
        msg['Subject'] = 'MIME attachments'
        msg.set_content('Plain text')
        msg.add_alternative('<p>HTML body</p>', subtype='html')
        msg.add_attachment(b'\x00\xff\x80\x10', maintype='application',
                           subtype='octet-stream', filename='sample.bin')
        return msg.as_bytes()

    def test_multipart_attachment_survives_parse_and_output(self):
        wire = self._multipart_fixture()
        parsed = Util.msg_from_file(io.BytesIO(wire), fullParse=True)
        encoded = Util.msg_as_string(parsed).encode('latin-1')
        original = BytesParser(policy=policy.default).parsebytes(wire)
        new = BytesParser(policy=policy.default).parsebytes(encoded)
        self.assertEqual(new.get_content_type(), original.get_content_type())
        self.assertEqual(
            [part.get_content_type() for part in new.walk()],
            [part.get_content_type() for part in original.walk()])
        self.assertEqual(
            list(new.iter_attachments())[0].get_payload(decode=True),
            list(original.iter_attachments())[0].get_payload(decode=True))

    def test_raw_eight_bit_body_is_not_reencoded(self):
        wire = b'From: alice@example.com\r\nSubject: Raw\r\n\r\nA\xffB\r\n'
        parsed = Util.msg_from_file(io.BytesIO(wire))
        result = Util.msg_as_string(parsed).encode('latin-1')
        self.assertIn(b'A\xffB', result)
        self.assertNotIn(b'A\xc3\xbfB', result)


if __name__ == '__main__':
    unittest.main()
