"""Byte-oriented I/O, fragmentation, failure and resource cleanup contracts."""
import errno
import importlib
import io
import socket
import struct
import sys
import unittest
try:
    from unittest import mock
except ImportError:
    import mock
from sonicprobe.libs import openvpn, xbstream


class SocketDouble(object):
    def __init__(self, data=b''):
        self.input = io.BytesIO(data)
        self.output = b''
        self.timeout = None
        self.closed = False
    def recv(self, size):
        return self.input.read(size)
    def sendall(self, data):
        self.output += data
    def gettimeout(self):
        return self.timeout
    def settimeout(self, value):
        self.timeout = value
    def close(self):
        self.closed = True
    def connect(self, address):
        pass


class OpenVPNContracts(unittest.TestCase):
    def client(self, data=b''):
        client = openvpn.OpenVPNMgmt('127.0.0.1', 1194)
        client._sock = SocketDouble(data)
        return client

    def test_lines_handle_bytes_lf_crlf_and_unicode(self):
        client = self.client(b'hello\r\nworld\n\xc3\xa9\r\n')
        self.assertEqual(client.readline(), 'hello')
        self.assertEqual(client.readline(), 'world')
        self.assertEqual(client.readline(), u'\xe9')

    def test_line_eof_raises_instead_of_looping(self):
        for value in (b'', b'partial'):
            with self.assertRaises(EOFError):
                self.client(value).readline()

    def test_command_uses_complete_binary_write(self):
        client = self.client()
        self.assertEqual(client.writeline('status'), 8)
        self.assertEqual(client._sock.output, b'status\r\n')

    def test_failed_connect_and_failed_greeting_close_socket(self):
        for error in (False, True):
            sock = SocketDouble()
            if error:
                sock.connect = mock.Mock(side_effect=socket.error('unavailable'))
            with mock.patch.object(openvpn.socket, 'socket', return_value=sock):
                client = openvpn.OpenVPNMgmt('127.0.0.1', 1194)
                with self.assertRaises((EOFError, socket.error)):
                    client.open()
            self.assertTrue(sock.closed)
            self.assertIsNone(client._sock)
            self.assertFalse(client._connected)

    def test_fragmented_marker_leaves_suffix_for_next_read(self):
        client = self.client(b'valueENDnext\n')
        self.assertEqual(client.readuntil('END', 0.1), 'value')
        self.assertIsNone(client._sock.gettimeout())
        self.assertEqual(client.readline(), 'next')

    def test_timeout_restored_when_marker_missing_or_socket_raises(self):
        for data in (b'partial', None):
            client = self.client(data or b'')
            if data is None:
                client._sock.recv = mock.Mock(side_effect=socket.timeout())
            with self.assertRaises((EOFError, socket.timeout)):
                client.readuntil('END', 0.1)
            self.assertIsNone(client._sock.gettimeout())

    def test_line_marker_discards_only_matching_line(self):
        client = self.client(b' first \r\nsecond\nEND\nnext\n')
        self.assertEqual(client.readlinesuntil('END', 0.1), 'firstsecond')
        self.assertIsNone(client._sock.gettimeout())
        self.assertEqual(client.readline(), 'next')

    def test_read_to_eof_and_kill_response(self):
        self.assertEqual(self.client(b'data').readuntil(), 'data')
        client = self.client(b'SUCCESS: killed\r\n')
        self.assertEqual(client.kill('example'), ['SUCCESS', ' killed'])
        self.assertEqual(client._sock.output, b'kill example\r\n')


class SerialContracts(unittest.TestCase):
    def setUp(self):
        # Optional hardware dependencies are replaced only during module loading.
        # No hardware or real XMODEM transfer is claimed by these tests.
        self.serial_driver = mock.Mock()
        with mock.patch.dict(sys.modules, {'serial': self.serial_driver, 'xmodem': mock.Mock()}):
            self.module = importlib.import_module('sonicprobe.libs.sp_serial')

    def tcp(self, data=b''):
        client = self.module.SPSerial.__new__(self.module.SPSerial)
        client.mode, client.socket = 'TCP', SocketDouble(data)
        client.eol, client.timeout = '\r', None
        return client

    def test_tcp_writes_bytes_and_telnet_break(self):
        client = self.tcp()
        self.assertEqual(client.writeline('hello'), 6)
        self.assertEqual(client.sendBreak(), 2)
        self.assertEqual(client.socket.output, b'hello\r\xff\xf3')

    def test_tcp_line_eof_terminates_and_returns_bytes(self):
        client = self.tcp(b'line\npartial')
        self.assertEqual(client.readline(), b'line\n')
        self.assertEqual(client.readline(), b'partial')
        self.assertEqual(client.readline(), b'')

    def test_fragmented_marker_and_original_blocking_timeout(self):
        client = self.tcp(b'valueENDsuffix')
        self.assertEqual(client.readuntil(b'END', 0.1), b'value')
        self.assertIsNone(client.socket.timeout)
        self.assertEqual(client.readuntil(), b'suffix')

    def test_line_eof_does_not_spin_and_timeout_is_restored(self):
        client = self.tcp()
        with self.assertRaises(EOFError):
            client.readlinesuntil(b'END', 0.1)
        self.assertIsNone(client.socket.timeout)

    def test_serial_timeout_restored_after_read_failure(self):
        client = self.module.SPSerial.__new__(self.module.SPSerial)
        client.mode = 'Serial'
        client.serial = mock.Mock(timeout=None)
        client.serial.read.side_effect = IOError('failed')
        with self.assertRaises(IOError):
            client.readuntil(b'END', 0.1)
        self.assertIsNone(client.serial.timeout)

    def test_tcp_close_and_connect_failure_release_resources(self):
        client = self.tcp(); client.close()
        self.assertTrue(client.socket.closed)
        sock = SocketDouble(); sock.connect = mock.Mock(side_effect=socket.error('no'))
        with mock.patch.object(self.module.socket, 'socket', return_value=sock), \
             mock.patch.object(self.module.socket, 'gethostbyname', return_value='127.0.0.1'):
            with self.assertRaises(socket.error):
                self.module.SPSerial('localhost:1234')
        self.assertTrue(sock.closed)


class XBStreamContracts(unittest.TestCase):
    @staticmethod
    def chunk(payload=None, name=b'file'):
        header = b'XBSTCK01\0' + (b'E' if payload is None else b'P') + struct.pack('<I', len(name)) + name
        if payload is not None:
            header += struct.pack('<QQI', len(payload), 0, 0) + payload
        return header

    def consume(self, data, write=None, tx=None, fragment=3):
        source, sink = io.BytesIO(data), io.BytesIO()
        callback = xbstream.XBStreamDefaultCallbacks(
            read=lambda n: source.read(min(n, fragment)), write=write or sink.write, tx=tx)
        reader = xbstream.XBStreamRead(callback, set_payload=True)
        while reader.is_streaming():
            reader()
        return reader, sink.getvalue()

    def test_binary_fragmented_payload_and_eof_chunks(self):
        data = self.chunk(b'payload') + self.chunk()
        reader, result = self.consume(data)
        self.assertEqual(result, data)
        self.assertEqual(reader.FILE_CHUNK_COUNT, {b'file': 2})

    def test_short_writes_neither_duplicate_nor_drop_bytes(self):
        output = []
        def write(data):
            output.append(data[:1]); return 1
        data = self.chunk(b'x' * 1500)
        self.consume(data, write=write)
        self.assertEqual(b''.join(output), data)

    def test_invalid_callback_progress_raises(self):
        for count in (0, -1, 1000000):
            with self.assertRaises(IOError):
                self.consume(self.chunk(), write=lambda data: count)

    def test_truncation_at_every_byte_is_rejected(self):
        data = self.chunk(b'hello')
        for size in range(1, len(data)):
            with self.assertRaises(EOFError):
                self.consume(data[:size])
        self.assertEqual(self.consume(b'')[1], b'')

    def test_empty_payload_and_callback_metadata(self):
        objects = []
        self.consume(self.chunk(b''), tx=lambda obj: objects.append(obj))
        self.assertEqual(objects[0].payload, b'')
        self.assertEqual(objects[0].name, b'file')
        self.assertEqual(objects[0].chunk_type, b'P')

    def test_callback_write_errors_propagate(self):
        failure = IOError(errno.EIO, 'failed')
        with self.assertRaises(IOError) as caught:
            self.consume(self.chunk(), write=mock.Mock(side_effect=failure))
        self.assertIs(caught.exception, failure)

    def test_tx_read_errors_are_not_swallowed(self):
        reader = xbstream.XBStreamRead(xbstream.XBStreamDefaultCallbacks(
            read=mock.Mock(side_effect=IOError(errno.EIO, 'failed')), write=mock.Mock()))
        with self.assertRaises(IOError):
            reader.tx_start()

    def test_unsupported_chunk_types_are_not_misread_as_payloads(self):
        data = self.chunk(b'data')
        for kind in (b'S', b'?'):
            with self.assertRaises(ValueError):
                self.consume(data[:9] + kind + data[10:])
