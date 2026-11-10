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

"""Small selectors-based event loop for the original TMDA SMTP proxy.

Only the socket dispatcher and delimiter-based chat interfaces used
by tmda-ofmipd are provided. This module is not a general asyncore
or asynchat compatibility implementation.
"""

import collections
import selectors
import socket
import sys
import traceback


socket_map = {}


class dispatcher:
    def __init__(self, sock=None):
        self.socket = sock
        self._closed = False
        self._listening = False
        if sock is not None:
            sock.setblocking(False)
            socket_map[id(self)] = self

    def create_socket(self, family, type):
        self.socket = socket.socket(family, type)
        self.socket.setblocking(False)
        socket_map[id(self)] = self

    def set_reuse_addr(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def bind(self, address):
        self.socket.bind(address)

    def listen(self, backlog):
        self.socket.listen(backlog)
        self._listening = True

    def accept(self):
        try:
            conn, addr = self.socket.accept()
        except BlockingIOError:
            return None
        conn.setblocking(False)
        return conn, addr

    def readable(self):
        return True

    def writable(self):
        return False

    def handle_accept(self):
        pass

    def handle_read(self):
        pass

    def handle_write(self):
        pass

    def handle_error(self):
        traceback.print_exc(file=sys.stderr)
        self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        socket_map.pop(id(self), None)
        if self.socket is not None:
            self.socket.close()

    def _dispatch_read(self):
        if self._listening:
            self.handle_accept()
        else:
            self.handle_read()


class async_chat(dispatcher):
    def __init__(self, sock):
        super().__init__(sock)
        self._terminator = None
        self._input_buffer = b''
        self._output = collections.deque()
        self._close_when_done = False

    def set_terminator(self, terminator):
        if not isinstance(terminator, (bytes, bytearray)) or not terminator:
            raise ValueError('terminator must be nonempty bytes')
        self._terminator = bytes(terminator)

    def push(self, data):
        if not isinstance(data, bytes):
            raise TypeError('SMTP output must be bytes')
        if data:
            self._output.append(data)

    def push_with_producer(self, producer):
        self._output.append(producer)

    def close_when_done(self):
        self._close_when_done = True

    def writable(self):
        return bool(self._output)

    def collect_incoming_data(self, data):
        raise NotImplementedError

    def found_terminator(self):
        raise NotImplementedError

    def handle_read(self):
        try:
            data = self.socket.recv(65536)
        except (BlockingIOError, InterruptedError):
            # Readiness can change between select() and recv().
            return
        if not data:
            self.close()
            return
        self._input_buffer += data
        while not self._closed and self._terminator:
            position = self._input_buffer.find(self._terminator)
            if position < 0:
                if self._input_buffer:
                    # Keep only the partial terminator while collecting
                    # large message bodies.
                    keep = min(len(self._terminator) - 1,
                               len(self._input_buffer))
                    if keep:
                        chunk, self._input_buffer = (
                            self._input_buffer[:-keep], self._input_buffer[-keep:])
                    else:
                        chunk, self._input_buffer = self._input_buffer, b''
                    if chunk:
                        self.collect_incoming_data(chunk)
                return
            chunk = self._input_buffer[:position]
            self._input_buffer = self._input_buffer[
                position + len(self._terminator):]
            if chunk:
                self.collect_incoming_data(chunk)
            self.found_terminator()

    def handle_write(self):
        while self._output:
            item = self._output[0]
            if not isinstance(item, bytes):
                self._output.popleft()
                more = item.more()
                if more:
                    self._output.appendleft(more)
                # Socket can be replaced by a STARTTLS producer.
                return
            try:
                sent = self.socket.send(item)
            except (BlockingIOError, InterruptedError):
                # Keep the unsent bytes queued until the socket is writable.
                return
            if not sent:
                return
            if sent == len(item):
                self._output.popleft()
            else:
                self._output[0] = item[sent:]
                return
        if self._close_when_done:
            self.close()


def loop(timeout=1.0, count=None):
    iterations = 0
    while socket_map and (count is None or iterations < count):
        iterations += 1
        with selectors.DefaultSelector() as selector:
            for obj in tuple(socket_map.values()):
                if obj._closed or obj.socket is None:
                    continue
                try:
                    events = (selectors.EVENT_READ if obj.readable() else 0)
                    events |= selectors.EVENT_WRITE if obj.writable() else 0
                    if events:
                        selector.register(obj.socket, events, obj)
                except (OSError, ValueError):
                    obj.close()
            if not selector.get_map():
                return
            events = selector.select(timeout)
        for key, mask in events:
            obj = key.data
            if obj._closed:
                continue
            try:
                if mask & selectors.EVENT_READ:
                    obj._dispatch_read()
                if not obj._closed and mask & selectors.EVENT_WRITE:
                    obj.handle_write()
            except (OSError, ValueError):
                obj.close()
            except Exception:
                obj.handle_error()


def close_all():
    for obj in tuple(socket_map.values()):
        obj.close()
