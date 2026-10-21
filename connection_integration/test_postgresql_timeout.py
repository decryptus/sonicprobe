"""Actual libpq timeout against a local peer that stalls during startup."""
import socket
import subprocess
import sys
import threading
import time
import unittest


class PostgreSQLTimeoutTests(unittest.TestCase):
    def test_explicit_timeout_bounds_stalled_startup(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(5)
        done = threading.Event()
        accepted = []

        def hold():
            try:
                connection, _ = listener.accept()
                accepted.append(True)
                with connection:
                    done.wait(5)
            except socket.timeout:
                pass

        thread = threading.Thread(target=hold)
        thread.start()
        code = '''
import psycopg2
from sonicprobe.libs.BackSQL.backpostgresql import connect_by_uri
try:
    connect_by_uri('postgresql://synthetic:synthetic@127.0.0.1:%d/test?connect_timeout=2')
except psycopg2.OperationalError:
    print('bounded-connection-error')
else:
    raise AssertionError('unexpected connection')
''' % listener.getsockname()[1]
        try:
            started = time.monotonic()
            result = subprocess.run([sys.executable, '-c', code], capture_output=True,
                                    text=True, timeout=4)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'bounded-connection-error')
            self.assertLess(time.monotonic() - started, 3.5)
            self.assertEqual(accepted, [True])
        finally:
            done.set()
            thread.join(6)
            listener.close()
        self.assertFalse(thread.is_alive())
