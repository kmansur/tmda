"""Ensure historic eight-bit mail headers stay byte-for-byte in TMDA logs."""
import os
import tempfile
import unittest
from email.message import Message

from TMDA.MessageLogger import MessageLogger


class MessageLoggerEncodingTests(unittest.TestCase):
    def test_legacy_eight_bit_subject_writes_original_octets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'message.log')
            message = Message()
            message['From'] = 'sender@example.org'
            message['Subject'] = 'caf\xe9'
            logger = MessageLogger(
                path, message, envrecip='recipient@example.org',
                action_msg='OK', msg_size=10,
            )
            logger.write()
            with open(path, 'rb') as stream:
                data = stream.read()
            self.assertIn(b'Subj: caf\xe9\n', data)
            self.assertNotIn(b'caf\xc3\xa9', data)


if __name__ == '__main__':
    unittest.main()
