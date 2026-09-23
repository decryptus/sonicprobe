"""Exercise the filesystem lock with distinct OS processes, not thread mocks."""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


class ProcessLockTests(unittest.TestCase):
    def test_two_processes_cannot_claim_the_same_pidfile(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory)
        lock_path = os.path.join(directory, 'daemon.pid')
        code = ("import os,sys\n"
                "from sonicprobe.libs.daemonize import take_file_lock\n"
                "path=sys.argv[1]\ncontent=str(os.getpid())+'\\n'\n"
                "own=path+'.'+str(os.getpid())\n"
                "with open(own,'w') as f: f.write(content)\n"
                "sys.stdin.read(1)\n"
                "sys.exit(0 if take_file_lock(own,path,content) else 1)\n")
        processes = [subprocess.Popen([sys.executable, '-c', code, lock_path],
                                      stdin=subprocess.PIPE) for _ in range(2)]
        try:
            for proc in processes:
                proc.stdin.write(b'x')
                proc.stdin.flush()
            deadline = time.time() + 5
            while any(proc.poll() is None for proc in processes) and time.time() < deadline:
                time.sleep(0.01)
            self.assertEqual(sorted(proc.poll() for proc in processes), [0, 1])
            winner = next(proc.pid for proc in processes if proc.returncode == 0)
            with open(lock_path) as stream:
                self.assertEqual(stream.read(), str(winner) + '\n')
            self.assertEqual(os.listdir(directory), ['daemon.pid'])
        finally:
            for proc in processes:
                proc.stdin.close()
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
