# -*- coding: utf-8 -*-
# Copyright (C) 2015-2019 Adrien Delle Cave
# SPDX-License-Identifier: GPL-3.0-or-later
"""sonicprobe.libs.openvpn"""

import logging
import socket

from six import ensure_binary, ensure_text


LOG = logging.getLogger("sonicprobe.helpers")


class OpenVPNMgmt(object): # pylint: disable=useless-object-inheritance
    def __init__(self, host, port, timeout = None, start_open = False):
        self._host      = host
        self._port      = port
        self._timeout   = timeout
        self._connected = False
        self._sock      = None
        self.eol        = '\r\n'

        if start_open:
            self.open()

    def open(self):
        if self._connected:
            return self

        self._sock      = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            if self._timeout is not None:
                self._sock.settimeout(self._timeout)
            self._sock.connect((self._host, self._port))
            self.readline()
        except BaseException:
            self.close()
            raise
        self._connected = True
        return self

    def close(self):
        self._connected = False
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        return self

    def writeline(self, data):
        payload = ensure_binary(data) + ensure_binary(self.eol)
        self._sock.sendall(payload)
        return len(payload)

    def readline(self):
        parts = []
        while True:
            char = self._sock.recv(1)
            if not char:
                raise EOFError('OpenVPN management connection closed before end of line')
            if char == b'\n':
                return ensure_text(b''.join(parts).rstrip(b'\r'))
            parts.append(char)

    def readlinesuntil(self, data=None, timeout=None):
        if not data:
            raise ValueError('a non-empty line marker is required')
        marker = ensure_text(data)
        previous = self._sock.gettimeout()
        try:
            if timeout is not None:
                self._sock.settimeout(timeout)
            parts = []
            while True:
                line = self.readline().strip()
                if marker in line:
                    return ''.join(parts)
                parts.append(line)
        finally:
            self._sock.settimeout(previous)

    def readuntil(self, data=None, timeout=None):
        marker = ensure_binary(data) if data else None
        previous = self._sock.gettimeout()
        try:
            if timeout is not None:
                self._sock.settimeout(timeout)
            parts = []
            tail = b''
            while True:
                char = self._sock.recv(1)
                if not char:
                    if marker:
                        raise EOFError('OpenVPN management connection closed before marker')
                    return ensure_text(b''.join(parts))
                parts.append(char)
                if marker:
                    tail = (tail + char)[-len(marker):]
                    if tail == marker:
                        return ensure_text(b''.join(parts)[:-len(marker)])
        finally:
            self._sock.settimeout(previous)

    def kill(self, client):
        LOG.debug("kill: %r", client)

        self.writeline("kill %s" % client)
        rs  = self.readline()

        LOG.debug("result: %r", rs)

        return rs.split(':', 1)
