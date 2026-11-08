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

"""Exercise the selectors-based SMTP transport without a real MTA."""

import socket
import unittest

from TMDA import SMTPEventLoop as events


class ChatFixture(events.async_chat):
    def __init__(self, sock):
        super().__init__(sock)
        self.parts = []
        self.messages = []
        self.set_terminator(b'\r\n')

    def collect_incoming_data(self, data):
        self.parts.append(data)

    def found_terminator(self):
        self.messages.append(b''.join(self.parts))
        self.parts.clear()


class Producer:
    def __init__(self, output, events_seen):
        self.output = output
        self.events_seen = events_seen

    def more(self):
        self.events_seen.append('callback')
        self.output.push(b'after\r\n')
        return b''


class SMTPEventLoopTests(unittest.TestCase):
    def setUp(self):
        self.client, server_sock = socket.socketpair()
        self.client.setblocking(False)
        self.chat = ChatFixture(server_sock)

    def tearDown(self):
        self.client.close()
        events.close_all()
        self.assertFalse(events.socket_map)

    def _tick(self, count=6):
        for _ in range(count):
            events.loop(timeout=0.001, count=1)

    def test_fragmented_terminator_and_pipelined_commands(self):
        self.client.sendall(b'HELO examp')
        self._tick()
        self.client.sendall(b'le\r')
        self._tick()
        self.client.sendall(b'\nNOOP\r\n')
        self._tick()
        self.assertEqual(self.chat.messages, [b'HELO example', b'NOOP'])

    def test_large_message_body_across_socket_reads(self):
        self.chat.set_terminator(b'\r\n.\r\n')
        data = b'Subject: test\r\n\r\n' + b'A' * 70000
        for start in range(0, len(data), 4000):
            self.client.sendall(data[start:start + 4000])
            self._tick(2)
        self.client.sendall(b'\r\n.\r\n')
        self._tick(5)
        self.assertEqual(self.chat.messages, [data])

    def test_producer_runs_only_after_queued_output(self):
        callbacks = []
        self.chat.push(b'before\r\n')
        self.chat.push_with_producer(Producer(self.chat, callbacks))
        self._tick(5)
        received = b''
        for _ in range(10):
            try:
                received += self.client.recv(4096)
            except BlockingIOError:
                pass
            self._tick(2)
        self.assertEqual(received, b'before\r\nafter\r\n')
        self.assertEqual(callbacks, ['callback'])

    def test_close_when_done_flushes_final_reply(self):
        self.chat.push(b'221 Bye\r\n')
        self.chat.close_when_done()
        self._tick(5)
        self.assertEqual(self.client.recv(4096), b'221 Bye\r\n')
        self.assertTrue(self.chat._closed)
        self.assertNotIn(id(self.chat), events.socket_map)


if __name__ == '__main__':
    unittest.main()
