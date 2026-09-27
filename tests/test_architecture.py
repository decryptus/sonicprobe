"""Execute generic utilities with interface imports forbidden."""
import subprocess
import sys
import unittest


class ArchitectureTests(unittest.TestCase):
    def test_generic_utilities_run_without_http_or_cli_imports(self):
        script = '''
import sys
try:
    import builtins
except ImportError:
    import __builtin__ as builtins
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.split('.')[0] in ('httpdis', 'dwho', 'argparse', 'curses'):
        raise AssertionError('interface import: ' + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
import os
import shutil
import tempfile
import threading
from sonicprobe import helpers
from sonicprobe.libs import daemonize, moresynchro, urisup, xys
from sonicprobe.libs.workerpool import WorkerPool
assert helpers.boolize('true')
assert urisup.uri_help_split('http://localhost/example')
assert xys.validate({'name': 'example'}, xys.load('name: !!str'))
lock = moresynchro.RWLock()
assert lock.acquire_write(0)
lock.release()
result, done = [], threading.Event()
pool = WorkerPool(max_workers=1, auto_gc=False)
try:
    pool.run(lambda: 42, result.append, complete=lambda value: done.set())
    assert done.wait(3)
    assert result == [42]
finally:
    pool.killall(3)
assert pool.count_workers() == 0
directory = tempfile.mkdtemp()
try:
    path = os.path.join(directory, 'pid')
    with daemonize.locked_pidfile(path) as pid:
        assert pid == os.getpid()
    assert not os.path.exists(path)
finally:
    shutil.rmtree(directory)
assert 'sonicprobe.libs.http_json_server' not in sys.modules
'''
        # communicate(timeout=...) is not available on Python 2.7. Run through a
        # parent watchdog so a boundary regression cannot leave this test hanging.
        process = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        import threading
        timer = threading.Timer(15, process.kill)
        timer.start()
        try:
            output, error = process.communicate()
            self.assertEqual(process.returncode, 0, error)
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
            process.wait()

    def test_legacy_http_shim_preserves_export_identity(self):
        from httpdis.ext import httpdis_json
        from sonicprobe.libs import http_json_server
        names = getattr(httpdis_json, '__all__', None)
        if names is None:
            names = [name for name in vars(httpdis_json) if not name.startswith('_')]
        for name in names:
            self.assertIs(getattr(http_json_server, name), getattr(httpdis_json, name))
