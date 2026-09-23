import threading
import unittest
from sonicprobe.libs.moresynchro import RWLock, ListLock
from sonicprobe.libs.keystore import Keystore

class LockTests(unittest.TestCase):
    def test_read_write_reentrancy_and_release(self):
        lock = RWLock()
        self.assertTrue(lock.acquire_read(0))
        self.assertFalse(lock.acquire_write(0))
        lock.release()
        self.assertTrue(lock.acquire_write(0))
        self.assertTrue(lock.acquire_read(0))
        lock.release(); lock.release()
        with self.assertRaises(RuntimeError):
            lock.release()

    def test_symbolic_lock_is_reentrant(self):
        lock = ListLock()
        self.assertTrue(lock.try_acquire('key'))
        self.assertTrue(lock.try_acquire('key'))
        lock.release('key'); lock.release('key')
        with self.assertRaises(RuntimeError):
            lock.release('key')

    def test_keystore_basic_values(self):
        store = Keystore()
        store.set('section', 'key', 42)
        self.assertEqual(store.get('section', 'key'), 42)
        store.reset('section')
        self.assertIsNone(store.get('section', 'key'))

    def test_keystore_remove_targets_nested_key(self):
        store = Keystore()
        store.set('section', 'key', 42)
        store.remove('section', 'key')
        self.assertIsNone(store.get('section', 'key'))

    def test_keystore_operations_do_not_leak_recursive_global_locks(self):
        store = Keystore()
        self.assertTrue(store.lock())
        store.set('section', 'key', 42)
        self.assertEqual(store.get('section', 'key'), 42)
        store.unlock()
        result = []
        def acquire():
            locked = store.try_lock(0.1)
            result.append(locked)
            if locked:
                store.unlock()
        thread = threading.Thread(target=acquire)
        thread.start(); thread.join(2)
        self.assertEqual(result, [True])

    def assert_global_lock_released_after_error(self, operation, error):
        store = Keystore(timeout=1)
        store.set('section', 'key', 42)
        entered = threading.Event()
        finished = threading.Event()
        cleanup = threading.Event()
        errors = []
        original_try_lock = store.try_lock

        def observed_try_lock(timeout=None):
            entered.set()
            return original_try_lock(timeout)

        def worker():
            try:
                operation(store)
            except Exception as exc:
                errors.append(type(exc))
            finally:
                finished.set()
                cleanup.wait(3)
                store.try_unlock()

        store.try_lock = observed_try_lock
        store.lock()
        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
        try:
            self.assertTrue(entered.wait(2), 'worker did not wait for global lock')
        finally:
            store.unlock()
        try:
            self.assertTrue(finished.wait(2), 'operation did not finish')
            self.assertEqual(errors, [error])
            acquired = original_try_lock(0.1)
            if acquired:
                store.unlock()
            self.assertTrue(acquired, 'exception leaked the global lock')
        finally:
            cleanup.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())

    def test_keystore_missing_section_releases_contended_global_lock(self):
        operations = [lambda s: s.updated_delta('missing'),
                      lambda s: s.has_key('missing', 'key'),
                      lambda s: s.remove('missing', 'key', lock=True),
                      lambda s: s.iteritems('missing'),
                      lambda s: s.iterkeys('missing'),
                      lambda s: s.itervalues('missing')]
        for operation in operations:
            self.assert_global_lock_released_after_error(operation, KeyError)

    def test_keystore_invalid_arguments_release_contended_global_lock(self):
        operations = [lambda s: s.add([]), lambda s: s.get([], 'key'),
                      lambda s: s.set([], 'key'), lambda s: s.exists([]),
                      lambda s: s.has_key([], 'key'), lambda s: s.delete([]),
                      lambda s: s.remove([], 'key'), lambda s: s.updated_at([]),
                      lambda s: s.updated_delta([]), lambda s: s.expired([], 1, lock=True),
                      lambda s: s.purge([]), lambda s: s.reset([]),
                      lambda s: s.acquire([]), lambda s: s.try_acquire([]),
                      lambda s: s.try_acquire('section', timeout='invalid')]
        for operation in operations:
            self.assert_global_lock_released_after_error(operation, TypeError)

    def test_keystore_section_lock_is_released_after_error(self):
        operations = [lambda s: s.get('section', [], lock=True),
                      lambda s: s.set('section', [], lock=True),
                      lambda s: s.has_key('section', [], lock=True),
                      lambda s: s.remove('section', [], lock=True)]
        for operation in operations:
            store = Keystore()
            store.set('section', 'key', 42)
            with self.assertRaises(TypeError):
                operation(store)
            result = []

            def worker():
                acquired = store.try_acquire('section', timeout=0.1, exists=True)
                result.append(acquired)
                if acquired:
                    store.release('section')

            thread = threading.Thread(target=worker)
            thread.daemon = True
            thread.start()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result, [True])
            self.assertEqual(store.get('section', 'key', lock=True), 42)

    def test_keystore_error_preserves_caller_owned_locks(self):
        store = Keystore()
        store.acquire('section')
        store.lock()
        try:
            with self.assertRaises(TypeError):
                store.get('section', [], lock=True)
            result = []

            def worker():
                acquired = store.try_lock(0.1)
                result.append(acquired)
                if acquired:
                    store.unlock()

            thread = threading.Thread(target=worker)
            thread.start()
            thread.join(2)
            self.assertEqual(result, [0])
        finally:
            store.unlock()
        result = []

        def section_worker():
            acquired = store.try_acquire('section', timeout=0.1, exists=True)
            result.append(acquired)
            if acquired:
                store.release('section')

        try:
            thread = threading.Thread(target=section_worker)
            thread.start()
            thread.join(2)
            self.assertEqual(result, [0])
        finally:
            store.release('section')

    def test_keystore_acquire_keeps_section_locked_until_release(self):
        for acquire in (lambda s: s.acquire('section'),
                        lambda s: s.try_acquire('section', timeout=0.1)):
            store = Keystore()
            self.assertTrue(acquire(store))
            result = []

            def worker():
                acquired = store.try_acquire('section', timeout=0.1, exists=True)
                result.append(acquired)
                if acquired:
                    store.release('section')

            try:
                thread = threading.Thread(target=worker)
                thread.start()
                thread.join(2)
                self.assertEqual(result, [0])
            finally:
                store.release('section')

    def test_keystore_missing_section_return_values(self):
        store = Keystore()
        self.assertEqual(store.get('missing', 'key', 'default', lock=True), 'default')
        self.assertEqual(store.updated_at('missing', 'default', lock=True), 'default')
        self.assertFalse(store.exists('missing', lock=True))
        self.assertIsNone(store.expired('missing', 10, lock=True))
        self.assertIsNone(store.acquire('missing', exists=True))
        self.assertIsNone(store.try_acquire('missing', exists=True))
        self.assertIs(store.delete('missing'), store)
        self.assertIs(store.purge('missing', lock=True), store)
        self.assertIs(store.reset('missing', lock=True), store)
