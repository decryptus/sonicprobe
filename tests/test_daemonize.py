"""PID lifecycle boundaries, including the historical launcher facade."""
import errno
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

try:
    from unittest import mock
except ImportError:
    import mock

from sonicprobe.libs import daemonize


class PidfileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = os.path.join(self.directory, 'daemon.pid')

    def test_claim_returns_pid_and_unlock_removes_own_file(self):
        self.assertEqual(daemonize.lock_pidfile(self.path), os.getpid())
        with open(self.path) as stream:
            self.assertEqual(stream.read(), '%s\n' % os.getpid())
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o644)
        self.assertEqual(os.listdir(self.directory), ['daemon.pid'])
        daemonize.unlock_pidfile(self.path)
        self.assertEqual(os.listdir(self.directory), [])

    def test_contention_raises_without_exiting_or_overwriting_owner(self):
        daemonize.lock_pidfile(self.path)
        with mock.patch.object(daemonize, 'remove_if_stale_pidfile'):
            with self.assertRaises(daemonize.PidfileLockError):
                daemonize.lock_pidfile(self.path)
        with open(self.path) as stream:
            self.assertEqual(stream.read(), '%s\n' % os.getpid())
        self.assertEqual(os.listdir(self.directory), ['daemon.pid'])

    def test_missing_directory_propagates_filesystem_error(self):
        with self.assertRaises(IOError) as caught:
            daemonize.lock_pidfile(os.path.join(self.directory, 'missing', 'daemon.pid'))
        self.assertEqual(caught.exception.errno, errno.ENOENT)

    def test_chmod_failure_cleans_temporary_file_and_preserves_error(self):
        error = OSError(errno.EPERM, 'denied')
        with mock.patch.object(daemonize.os, 'chmod', side_effect=error):
            with self.assertRaises(OSError) as caught:
                daemonize.lock_pidfile(self.path)
        self.assertIs(caught.exception, error)
        self.assertEqual(os.listdir(self.directory), [])

    def test_write_failure_closes_and_cleans_temporary_file(self):
        error = IOError(errno.ENOSPC, 'full')
        real_open = open
        stream = mock.MagicMock()
        def failing_write(value):
            raise error
        def open_temporary(path, mode):
            handle = real_open(path, mode)
            stream.__enter__.return_value = stream
            stream.__exit__.side_effect = lambda *args: handle.close()
            stream.write.side_effect = failing_write
            return stream
        with mock.patch.object(daemonize, 'open', side_effect=open_temporary, create=True):
            with mock.patch.object(daemonize, 'remove_if_stale_pidfile'):
                with self.assertRaises(IOError) as caught:
                    daemonize.lock_pidfile(self.path)
        self.assertIs(caught.exception, error)
        self.assertEqual(stream.__exit__.call_count, 1)
        self.assertEqual(os.listdir(self.directory), [])

    def test_open_failure_does_not_delete_an_existing_temporary_path(self):
        temporary = self.path + '.' + str(os.getpid())
        with open(temporary, 'w') as stream:
            stream.write('keep')
        with mock.patch.object(daemonize, 'open', side_effect=IOError(errno.EACCES, 'denied'), create=True):
            with mock.patch.object(daemonize, 'remove_if_stale_pidfile'):
                with self.assertRaises(IOError):
                    daemonize.lock_pidfile(self.path)
        with open(temporary) as stream:
            self.assertEqual(stream.read(), 'keep')

    def test_legacy_facade_still_returns_pid_or_exits_one(self):
        self.assertEqual(daemonize.lock_pidfile_or_die(self.path), os.getpid())
        with mock.patch.object(daemonize, 'remove_if_stale_pidfile'):
            with self.assertRaises(SystemExit) as caught:
                daemonize.lock_pidfile_or_die(self.path)
        self.assertEqual(caught.exception.code, 1)
        with self.assertRaises(SystemExit) as caught:
            daemonize.lock_pidfile_or_die(os.path.join(self.directory, 'missing', 'pid'))
        self.assertEqual(caught.exception.code, 1)

    def test_embedded_context_does_not_daemonize_and_releases_on_exception(self):
        with mock.patch.object(daemonize, 'daemonize') as fork:
            with self.assertRaises(ValueError):
                with daemonize.locked_pidfile(self.path) as pid:
                    self.assertEqual(pid, os.getpid())
                    self.assertTrue(os.path.isfile(self.path))
                    raise ValueError('application failed')
            fork.assert_not_called()
        self.assertFalse(os.path.exists(self.path))

    def test_failed_context_does_not_unlock_another_owner(self):
        with mock.patch.object(daemonize, 'lock_pidfile', side_effect=daemonize.PidfileLockError('busy')):
            with mock.patch.object(daemonize, 'unlock_pidfile') as unlock:
                with self.assertRaises(daemonize.PidfileLockError):
                    with daemonize.locked_pidfile(self.path):
                        self.fail('entered without lock')
                unlock.assert_not_called()

    def test_legacy_context_keeps_daemon_and_foreground_behavior(self):
        for foreground in (False, True):
            with mock.patch.object(daemonize, 'daemonize') as fork:
                with daemonize.pidfile_context(self.path, foreground=foreground) as result:
                    self.assertIsNone(result)
                    self.assertTrue(os.path.isfile(self.path))
                self.assertEqual(fork.call_count, int(not foreground))
            self.assertFalse(os.path.exists(self.path))

    @unittest.skipUnless(os.path.exists('/proc/self') and
                         os.readlink('/proc/self') == str(os.getpid()),
                         'requires /proc matching the process PID namespace')
    def test_distinct_processes_contend_through_new_primitive(self):
        code = ("import os,sys\n"
                "from sonicprobe.libs.daemonize import lock_pidfile,PidfileLockError,unlock_pidfile\n"
                "path=sys.argv[1]\n"
                "sys.stdin.read(1)\n"
                "try:\n lock_pidfile(path); result='owned'\n"
                "except PidfileLockError:\n result='busy'\n"
                "with open(sys.argv[2]+'.tmp','w') as stream: stream.write(result)\n"
                "os.rename(sys.argv[2]+'.tmp',sys.argv[2])\n"
                "sys.stdin.read(1)\n"
                "if result=='owned': unlock_pidfile(path)\n")
        results = [os.path.join(self.directory, 'result-%s' % index) for index in range(2)]
        processes = [subprocess.Popen([sys.executable, '-c', code, self.path, result],
                                      stdin=subprocess.PIPE) for result in results]
        try:
            for process in processes:
                process.stdin.write(b'x')
                process.stdin.flush()
            deadline = time.time() + 5
            while not all(os.path.isfile(result) for result in results) and time.time() < deadline:
                time.sleep(0.01)
            values = []
            for result in results:
                with open(result) as stream:
                    values.append(stream.read())
            self.assertEqual(sorted(values), ['busy', 'owned'])
            for process in processes:
                process.stdin.write(b'x')
                process.stdin.flush()
            deadline = time.time() + 5
            while any(p.poll() is None for p in processes) and time.time() < deadline:
                time.sleep(0.01)
            self.assertEqual([p.poll() for p in processes], [0, 0])
            self.assertFalse(os.path.exists(self.path))
        finally:
            for process in processes:
                process.stdin.close()
                if process.poll() is None:
                    process.kill()
                process.wait()
