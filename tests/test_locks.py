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
