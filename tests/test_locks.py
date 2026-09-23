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

        def worker():
            entered.set()
            try:
                operation(store)
            except Exception as exc:
                errors.append(type(exc))
            finally:
                finished.set()
                cleanup.wait(3)
                store.try_unlock()

        store.lock()
        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
        try:
            self.assertTrue(entered.wait(2), 'worker did not start')
            self.assertFalse(finished.wait(0.02), 'operation bypassed global lock')
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

    def test_keystore_recursive_global_lock_blocks_operations_until_final_release(self):
        store = Keystore(timeout=2)
        store.lock()
        store.try_lock()
        store.unlock()
        entered, finished = threading.Event(), threading.Event()
        def worker():
            entered.set()
            store.set('section', 'key', 42)
            finished.set()
        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertFalse(finished.wait(0.05))
        finally:
            store.unlock()
            thread.join(3)
        self.assertTrue(finished.is_set())
        self.assertEqual(store.get('section', 'key'), 42)

    def test_list_lock_rejects_release_by_another_thread(self):
        lock = ListLock()
        lock.try_acquire('key')
        errors = []
        def worker():
            try:
                lock.release('key')
            except RuntimeError:
                errors.append('rejected')
            errors.append(lock.try_acquire('key'))
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(2)
        self.assertEqual(errors, ['rejected', False])
        lock.release('key')

    def test_rwlock_writer_timeout_wakes_readers_without_releasing_existing_reader(self):
        lock = RWLock()
        lock.acquire_read()
        waiting_writer, waiting_reader = threading.Event(), threading.Event()
        done_writer, done_reader = threading.Event(), threading.Event()
        condition = lock._RWLock__condition
        original_wait = condition.wait
        def observed_wait(timeout=None):
            if threading.current_thread().name == 'waiting-writer':
                waiting_writer.set()
            else:
                waiting_reader.set()
            return original_wait(timeout)
        condition.wait = observed_wait
        results = []
        def writer():
            acquired = lock.acquire_write(0.3)
            results.append(('writer', acquired))
            if acquired:
                lock.release()
            done_writer.set()
        def reader():
            acquired = lock.acquire_read(3)
            results.append(('reader', acquired))
            if acquired:
                lock.release()
            done_reader.set()
        writer_thread = threading.Thread(target=writer, name='waiting-writer')
        reader_thread = threading.Thread(target=reader)
        writer_thread.start()
        try:
            self.assertTrue(waiting_writer.wait(1))
            reader_thread.start()
            self.assertTrue(waiting_reader.wait(1))
            self.assertTrue(done_writer.wait(2))
            self.assertTrue(done_reader.wait(1), 'reader was not notified of writer timeout')
        finally:
            lock.release()
            writer_thread.join(4)
            if reader_thread.ident is not None:
                reader_thread.join(4)
        self.assertIn(('writer', None), results)
        self.assertIn(('reader', True), results)

    def test_rwlock_interrupted_writer_does_not_leave_a_pending_writer(self):
        try:
            from unittest import mock
        except ImportError:
            import mock
        lock = RWLock()
        lock.acquire_read()
        errors = []
        def writer():
            try:
                lock.acquire_write()
            except KeyboardInterrupt:
                errors.append('interrupted')
        with mock.patch.object(lock._RWLock__condition, 'wait', side_effect=KeyboardInterrupt):
            thread = threading.Thread(target=writer)
            thread.start()
            thread.join(2)
        lock.release()
        self.assertEqual(errors, ['interrupted'])
        self.assertTrue(lock.acquire_read(0))
        lock.release()
        self.assertTrue(lock.acquire_write(0))
        lock.release()

    def test_keystore_global_lock_waits_for_an_inflight_operation(self):
        store = Keystore()
        entered, resume = threading.Event(), threading.Event()
        class SlowKey(object):
            def __hash__(self):
                entered.set()
                resume.wait(3)
                return 42
        key = SlowKey()
        thread = threading.Thread(target=lambda: store.set('section', key, 'value', lock=True))
        thread.daemon = True
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            acquired = store.try_lock(0.05)
            if acquired:
                store.unlock()
            self.assertFalse(acquired, 'global lock overlapped an existing operation')
        finally:
            resume.set()
            thread.join(3)
        self.assertTrue(store.try_lock(0.1))
        store.unlock()

    def test_keystore_concurrent_first_writes_preserve_both_keys(self):
        try:
            from unittest import mock
        except ImportError:
            import mock
        store = Keystore()
        entered, resume, second_entered = threading.Event(), threading.Event(), threading.Event()
        original = threading.RLock
        def create():
            entered.set()
            resume.wait(3)
            return original()
        def second():
            second_entered.set()
            store.set('section', 'second', 2, lock=True)
        with mock.patch('sonicprobe.libs.keystore.threading.RLock', side_effect=create):
            first_thread = threading.Thread(target=lambda: store.set('section', 'first', 1, lock=True))
            second_thread = threading.Thread(target=second)
            first_thread.start()
            self.assertTrue(entered.wait(1))
            second_thread.start()
            self.assertTrue(second_entered.wait(1))
            resume.set()
            first_thread.join(3)
            second_thread.join(3)
        self.assertEqual(dict(store.iteritems('section')), {'first': 1, 'second': 2})
