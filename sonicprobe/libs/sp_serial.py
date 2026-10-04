# -*- coding: utf-8 -*-
# Copyright (C) 2015-2019 Adrien Delle Cave
# SPDX-License-Identifier: GPL-3.0-or-later
"""sonicprobe.libs.sp_serial"""

import logging
import socket

from time import sleep
from six import ensure_binary

import serial
from xmodem import XMODEM


LOG = logging.getLogger("sp_serial.%s" % __name__)

class SPSerial(object): # pylint: disable=useless-object-inheritance
    def __init__(self,
                 port               = None,
                 baudrate           = 9600,
                 bytesize           = 8,
                 parity             = 'N',
                 stopbits           = 1,
                 timeout            = None,
                 xonxoff            = False,
                 rtscts             = False,
                 writeTimeout       = None,
                 dsrdtr             = False,
                 eol                = '\r'):

        if port is None or ":" not in port:
            LOG.debug("Using serial port %r", port)
            self.mode = 'Serial'
            self.serial = serial.Serial(
                port         = port,
                baudrate     = baudrate,
                bytesize     = bytesize,
                parity       = parity,
                stopbits     = stopbits,
                timeout      = timeout,
                xonxoff      = xonxoff,
                rtscts       = rtscts,
                writeTimeout = writeTimeout,
                dsrdtr       = dsrdtr)
        else:
            LOG.debug("Using tcp port %r", port)
            self.mode = 'TCP'
            host, tcpport = port.split(':')
            tcpport = int(tcpport)
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self.socket.settimeout(1 if timeout is None else timeout)
                self.socket.connect((socket.gethostbyname(host), tcpport))
                # Retain the historical transport handle, now in binary mode.
                self.serial = self.socket.makefile('rwb', 0)
            except BaseException:
                self.socket.close()
                raise

        self.eol            = eol
        self.progressbar    = None
        self.progresslen    = 0
        self.timeout        = None

    def read(self, size):
        if self.mode == 'Serial':
            return self.serial.read(size)
        return self.socket.recv(size)

    def readline(self):
        if self.mode == 'Serial':
            return self.serial.readline()
        parts = []
        try:
            while True:
                char = self.socket.recv(1)
                if not char:
                    break
                parts.append(char)
                if char == b'\n':
                    break
        except socket.timeout:
            pass
        return b''.join(parts)

    def close(self):
        if self.mode == 'Serial':
            self.serial.close()
        else:
            try:
                stream = getattr(self, 'serial', None)
                if stream is not None:
                    stream.close()
            finally:
                self.socket.close()

    def write(self, data):
        data = ensure_binary(data)
        if self.mode == 'TCP':
            self.socket.sendall(data)
            return len(data)
        result = self.serial.write(data)
        self.serial.flush()
        return result

    def writeline(self, data):
        return self.write(ensure_binary(data) + ensure_binary(self.eol))

    def sendBreak(self, duration = 1):
        if self.mode == 'Serial':
            return self.serial.sendBreak(duration)
        return self.write(b"\xFF\xF3") # Telnet IAC BREAK

    def setTmpTimeout(self, timeout):
        if self.mode == 'Serial':
            self.timeout = self.serial.timeout
            if timeout is not None:
                self.serial.timeout = timeout
        else:
            self.timeout = self.socket.gettimeout()
            if timeout is not None:
                self.socket.settimeout(timeout)

    def restoreTimeout(self):
        if self.mode == 'Serial':
            self.serial.timeout = self.timeout
        else:
            self.socket.settimeout(self.timeout)

    def readlinesuntil(self, data = None, timeout = None):
        if not data:
            raise ValueError('a non-empty line marker is required')
        marker = ensure_binary(data)
        self.setTmpTimeout(timeout)
        try:
            parts = []
            while True:
                line = self.readline()
                if not line:
                    raise EOFError('Serial/TCP stream ended or timed out before marker')
                line = line.strip()
                if marker in line:
                    return b''.join(parts)
                parts.append(line)
        finally:
            self.restoreTimeout()

    def readuntil(self, data = None, timeout = None):
        marker = ensure_binary(data) if data else None
        self.setTmpTimeout(timeout)
        try:
            parts = []
            tail = b''
            while True:
                char = self.read(1)
                if not char:
                    if marker:
                        raise EOFError('Serial/TCP stream ended or timed out before marker')
                    return b''.join(parts)
                parts.append(char)
                if marker:
                    tail = (tail + char)[-len(marker):]
                    if tail == marker:
                        return b''.join(parts)[:-len(marker)]
        finally:
            self.restoreTimeout()

    def getc(self, size, timeout=1): # pylint: disable=unused-argument
        r = self.read(size)
        LOG.debug("RXc bytes: %d", len(r) if r else 0)
        return r

    def putc(self, data, timeout=1): # pylint: disable=unused-argument
        LOG.debug("TXc bytes: %d", len(data))
        r = self.write(data)
        sleep(0.001)

        if self.progressbar:
            self.progresslen += len(data)
            if self.progresslen <= self.progressbar.maxval:
                self.progressbar.update(self.progresslen)

        return r

    def xmodem(self, progressbar=None, mode = 'xmodem', pad = b'\x1a'):
        self.progressbar = progressbar
        self.progresslen = 0

        return XMODEM(getc = self.getc, putc = self.putc, mode = mode, pad = pad)
