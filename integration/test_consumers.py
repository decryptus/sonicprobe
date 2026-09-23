"""Exercise real DWho dispatch and the lock contracts used by consumers."""
import threading
import unittest
from types import SimpleNamespace

from dwho.classes import inotify, notifiers
from sonicprobe.libs.workerpool import WorkerPool
from sonicprobe.libs.keystore import Keystore


class ConsumerTests(unittest.TestCase):
    def test_dwho_async_notifications_use_real_workers_and_keep_all_payloads(self):
        push = notifiers.DWhoPushNotifications()
        received = []
        def receiver(name, cfg, uri, nvars, tpl):
            received.append((name, nvars['_NAME_'], nvars['_VARS_']['value']))
        for name in ('first', 'second'):
            push.notifications[name] = {
                'cfg': {'general': {'uri': 'http://localhost/', 'async': True}},
                'tpl': None, 'tags': set(['all']), 'notifiers': [receiver]}
        for value in (1, 2):
            push._run({'value': value}, names=['first', 'second'])
            self.assertIsNone(push.workerpool)
        self.assertEqual(received, [('first', 'first', 1), ('second', 'second', 1),
                                    ('first', 'first', 2), ('second', 'second', 2)])

    def test_dwho_inotify_dispatch_executes_with_the_real_pool(self):
        pool = WorkerPool(max_workers=2, auto_gc=False)
        self.addCleanup(pool.killall, 2)
        done, received = threading.Event(), []
        def make_call(config, conf_path, event, filepath):
            def call():
                received.append((filepath, conf_path.plugins))
                done.set()
            return call
        watcher = SimpleNamespace(config={}, workerpool=pool)
        plugin = SimpleNamespace(PLUGIN_NAME='example')
        path = inotify.DWhoInotifyCfgPath('/tmp', plugins=[plugin])
        handler = inotify.DWhoInotifyEventHandler(dw_inotify=watcher, plugs_class=make_call)
        handler.call_plugins(path, SimpleNamespace(pathname='/tmp/example'),
                             include_plugins=['example'])
        self.assertTrue(done.wait(2))
        pool.tasks.join()
        self.assertEqual(received, [('/tmp/example', [plugin])])

    def test_auton_and_covenant_modules_keep_read_write_lock_contracts(self):
        from auton.modules.job import JobModule
        from covenant.modules.metrics import MetricsModule
        from covenant.modules.probes import ProbesModule
        for module in (JobModule, MetricsModule, ProbesModule):
            lock = module.LOCK
            self.assertTrue(lock.acquire_read(0))
            try:
                self.assertFalse(lock.acquire_write(0))
                other_reader = []
                def read():
                    acquired = lock.acquire_read(0.2)
                    other_reader.append(acquired)
                    if acquired:
                        lock.release()
                thread = threading.Thread(target=read)
                thread.start()
                thread.join(1)
                self.assertEqual(other_reader, [True])
            finally:
                lock.release()
            self.assertTrue(lock.acquire_write(0))
            self.assertTrue(lock.acquire_read(0))
            lock.release()
            lock.release()

    def test_nsaproxy_section_acquisition_pattern(self):
        # NSAProxy uses try_acquire(name, timeout, exists=False), then release(name).
        # This contract test does not certify the whole NSAProxy application.
        store = Keystore()
        self.assertTrue(store.try_acquire('example.org', timeout=0.2, exists=False))
        result = []
        def worker():
            acquired = store.try_acquire('example.org', timeout=0.05, exists=True)
            result.append(acquired)
            if acquired:
                store.release('example.org')
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(1)
        self.assertEqual(result, [0])
        store.release('example.org')
        self.assertTrue(store.try_acquire('example.org', timeout=0.2, exists=True))
        store.release('example.org')
