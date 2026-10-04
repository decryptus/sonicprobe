"""Ownership, deletion and recreation with coordinated real threads."""
import threading
import unittest
try:
    from unittest import mock
except ImportError:
    import mock
from sonicprobe.libs.keystore import Keystore


class KeystoreLifecycleTests(unittest.TestCase):
    def start_call(self, function):
        entered, done = threading.Event(), threading.Event()
        result = []
        def run():
            entered.set()
            try:
                result.append(function())
            except BaseException as error:
                result.append(error)
            finally:
                done.set()
        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()
        self.assertTrue(entered.wait(1))
        return thread, done, result

    def finish_call(self, call):
        thread, done, result = call
        thread.join(2)
        self.assertFalse(thread.is_alive(), 'operation did not terminate')
        self.assertTrue(done.is_set())
        if result and isinstance(result[0], BaseException):
            raise result[0]
        return result[0]

    def try_other(self, store, name='section', exists=True):
        def acquire():
            acquired = store.try_acquire(name, timeout=0.05, exists=exists)
            if acquired:
                store.release(name)
            return acquired
        return self.finish_call(self.start_call(acquire))

    def test_deleted_recreated_section_keeps_outstanding_owner(self):
        store = Keystore()
        store.acquire('section')
        try:
            store.delete('section')
            store.set('section', 'value', 'replacement')
            self.assertEqual(self.try_other(store), 0)
        finally:
            store.release('section')
        self.assertTrue(self.try_other(store))
        self.assertEqual(store.get('section', 'value'), 'replacement')

    def test_recursive_owner_survives_delete_recreate_until_last_release(self):
        store = Keystore()
        store.acquire('section'); store.acquire('section')
        store.delete('section'); store.add('section', lock=True)
        store.release('section')
        try:
            self.assertEqual(self.try_other(store), 0)
        finally:
            store.release('section')
        self.assertTrue(self.try_other(store))

    def test_delete_without_recreate_allows_owner_to_release(self):
        store = Keystore(); store.acquire('section')
        store.delete('section')
        self.assertIsNone(self.try_other(store))
        store.release('section')
        self.assertFalse(store.exists('section'))
        self.assertTrue(self.try_other(store, exists=False))

    def test_opt_out_delete_does_not_replace_someone_elses_lock(self):
        store = Keystore(); store.acquire('section')
        def replace():
            store.delete('section', lock=False)
            store.set('section', 'value', 42, lock=False)
        self.finish_call(self.start_call(replace))
        try:
            self.assertEqual(self.try_other(store), 0)
        finally:
            store.release('section')
        self.assertTrue(self.try_other(store))

    def test_nonblocking_acquire_does_not_block_during_exists_check(self):
        store = Keystore(); store.acquire('section')
        def acquire():
            acquired = store.acquire('section', blocking=False, exists=True)
            if acquired: store.release('section')
            return acquired
        call = self.start_call(acquire)
        try:
            self.assertTrue(call[1].wait(1), 'nonblocking acquisition blocked')
            self.assertIs(call[2][0], False)
        finally:
            store.release('section')
            call[0].join(2)

    def test_nonblocking_and_timed_acquire_include_global_contention(self):
        store = Keystore(); store.add('section'); store.lock()
        def attempts():
            return (store.acquire('section', blocking=False),
                    store.try_acquire('section'), store.try_acquire('section', timeout=0.05))
        call = self.start_call(attempts)
        try:
            self.assertTrue(call[1].wait(1))
            self.assertEqual(call[2], [(False, False, 0)])
        finally:
            store.unlock(); call[0].join(2)

    def test_invalid_nonblocking_arguments_fail_without_waiting_or_leaks(self):
        store = Keystore(); store.lock()
        def invalid():
            for operation in (lambda: store.try_acquire([]),
                              lambda: store.try_acquire('section', timeout='invalid'),
                              lambda: store.acquire([], blocking=False)):
                with self.assertRaises(TypeError): operation()
            return True
        call = self.start_call(invalid)
        try:
            self.assertTrue(call[1].wait(1))
        finally:
            store.unlock()
        self.assertTrue(self.finish_call(call))
        self.assertTrue(store.try_lock()); store.unlock()

    def test_waiting_get_observes_deletion_as_missing(self):
        store = Keystore(); store.acquire('section')
        waiting = threading.Event()
        original = store._wait
        def wait(deadline):
            waiting.set(); return original(deadline)
        with mock.patch.object(store, '_wait', side_effect=wait):
            call = self.start_call(lambda: store.get('section', 'value', 'missing', lock=True))
            try:
                self.assertTrue(waiting.wait(1))
                store.delete('section')
            finally:
                store.release('section')
            self.assertEqual(self.finish_call(call), 'missing')

    def test_waiting_exists_acquire_does_not_claim_a_deleted_section(self):
        store = Keystore(); store.acquire('section')
        waiting = threading.Event(); original = store._wait
        def wait(deadline):
            waiting.set(); return original(deadline)
        def acquire():
            value = store.acquire('section', exists=True)
            if value: store.release('section')
            return value
        with mock.patch.object(store, '_wait', side_effect=wait):
            call = self.start_call(acquire)
            try:
                self.assertTrue(waiting.wait(1)); store.delete('section')
                self.assertTrue(call[1].wait(1))
            finally:
                store.release('section')
            self.assertIsNone(self.finish_call(call))

    def test_waiting_set_recreates_after_delete_without_lost_lock(self):
        store = Keystore(); store.acquire('section')
        waiting = threading.Event(); original = store._wait
        def wait(deadline):
            waiting.set(); return original(deadline)
        with mock.patch.object(store, '_wait', side_effect=wait):
            call = self.start_call(lambda: store.set('section', 'value', 42, lock=True))
            try:
                self.assertTrue(waiting.wait(1)); store.delete('section')
            finally:
                store.release('section')
            self.finish_call(call)
        self.assertEqual(store.get('section', 'value'), 42)
        self.assertTrue(self.try_other(store))

    def test_global_lock_waits_for_explicit_section_owner_without_inversion(self):
        store = Keystore(); store.acquire('section')
        acquired, release = threading.Event(), threading.Event()
        waiting = threading.Event(); original = store._wait
        def wait(deadline):
            waiting.set(); return original(deadline)
        def global_owner():
            value = store.lock()
            if value:
                acquired.set(); release.wait(2); store.unlock()
            return value
        with mock.patch.object(store, '_wait', side_effect=wait):
            call = self.start_call(global_owner)
            try:
                self.assertTrue(waiting.wait(1)); self.assertFalse(acquired.is_set())
                store.set('section', 'value', 42, lock=True)
            finally:
                store.release('section')
            try:
                self.assertTrue(acquired.wait(1))
            finally:
                release.set()
            self.assertTrue(self.finish_call(call))

    def test_contended_promotion_fails_without_releasing_owned_section(self):
        store = Keystore(); store.acquire('first')
        ready, release = threading.Event(), threading.Event()
        def owner():
            store.acquire('second'); ready.set(); release.wait(2); store.release('second')
        call = self.start_call(owner)
        try:
            self.assertTrue(ready.wait(1))
            self.assertIsNone(store.lock())
            self.assertEqual(self.try_other(store, 'first'), 0)
        finally:
            release.set(); self.finish_call(call)
        self.assertTrue(store.lock()); store.unlock(); store.release('first')

    def test_global_waiters_do_not_take_ownership_from_each_other(self):
        store = Keystore(); store.acquire('section')
        first, release = threading.Event(), threading.Event()
        owners = []; guard = threading.Lock()
        def own():
            self.assertTrue(store.lock())
            try:
                with guard:
                    owners.append(threading.current_thread().name)
                    first.set()
                release.wait(2)
            finally:
                store.unlock()
        calls = [self.start_call(own), self.start_call(own)]
        store.release('section')
        try:
            self.assertTrue(first.wait(1))
            # The second waiter must remain blocked until the owner releases.
            self.assertFalse(calls[0][1].wait(0.05))
            self.assertFalse(calls[1][1].is_set())
            self.assertEqual(len(owners), 1)
        finally:
            release.set()
        for call in calls: self.finish_call(call)
        self.assertEqual(len(owners), 2)

    def test_interrupted_wait_cleans_registration(self):
        store = Keystore(); ready, release = threading.Event(), threading.Event()
        def own():
            store.acquire('section'); ready.set(); release.wait(2); store.release('section')
        call = self.start_call(own)
        try:
            self.assertTrue(ready.wait(1))
            with mock.patch.object(store, '_wait', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt): store.try_acquire('section', 1)
        finally:
            release.set(); self.finish_call(call)
        self.assertTrue(store.try_acquire('section')); store.release('section')
        store.delete('section')
        self.assertEqual(store._Keystore__lock, {})

    def test_deleted_idle_sections_do_not_accumulate_lock_records(self):
        store = Keystore()
        for name in range(100):
            store.acquire(name); store.delete(name); store.release(name)
        self.assertEqual(store.list(), [])
        self.assertEqual(store._Keystore__lock, {})
        self.assertEqual(store._Keystore__owners, {})
        self.assertEqual(store._Keystore__waiters, {})

    def test_missing_remove_does_not_create_a_timestamp_only_section(self):
        store = Keystore()
        for enabled in (False, True):
            with self.assertRaises(KeyError): store.remove('missing', 'key', lock=enabled)
        self.assertIsNone(store.updated_at('missing'))
        self.assertFalse(store.exists('missing'))

    def test_wrong_thread_cannot_release_a_deleted_owned_section(self):
        store = Keystore(); store.acquire('section'); store.delete('section')
        def release():
            with self.assertRaises(RuntimeError): store.release('section')
            return True
        try:
            self.assertTrue(self.finish_call(self.start_call(release)))
        finally:
            store.release('section')

    def test_concurrent_recreation_preserves_each_owned_transaction(self):
        store = Keystore()
        start = threading.Event()
        def worker(number):
            start.wait(2)
            for step in range(40):
                store.acquire('section')
                try:
                    store.delete('section')
                    store.set('section', 'value', (number, step), lock=True)
                    self.assertEqual(store.get('section', 'value', lock=True), (number, step))
                finally:
                    store.release('section')
            return True
        calls = [self.start_call(lambda n=n: worker(n)) for n in range(3)]
        start.set()
        for call in calls: self.assertTrue(self.finish_call(call))
        store.delete('section')
        self.assertEqual(store._Keystore__lock, {})

    def test_global_waiter_timeout_releases_new_readers(self):
        store = Keystore(); store.acquire('section')
        waiting = threading.Event(); original = store._wait
        def wait(deadline):
            waiting.set(); return original(deadline)
        with mock.patch.object(store, '_wait', side_effect=wait):
            writer = self.start_call(lambda: store.try_lock(0.1))
            try:
                self.assertTrue(waiting.wait(1))
                reader = self.start_call(lambda: store.get('section', 'value', 'default'))
                self.assertEqual(self.finish_call(writer), 0)
                self.assertEqual(self.finish_call(reader), 'default')
            finally:
                store.release('section')

    def test_timed_acquire_bounds_metadata_mutex_contention(self):
        store = Keystore(); entered, resume = threading.Event(), threading.Event()
        class SlowKey(object):
            def __hash__(self):
                entered.set(); resume.wait(2); return 42
        call = self.start_call(lambda: store.set('section', SlowKey(), 1))
        try:
            self.assertTrue(entered.wait(1))
            self.assertEqual(store.try_acquire('other', timeout=0.05), 0)
        finally:
            resume.set(); self.finish_call(call)

    def test_blocking_acquire_preserves_configured_global_timeout(self):
        store = Keystore(timeout=0.05); store.lock()
        def acquire():
            with self.assertRaises(RuntimeError): store.acquire('section')
            return True
        call = self.start_call(acquire)
        try:
            self.assertTrue(call[1].wait(1))
        finally:
            store.unlock()
        self.assertTrue(self.finish_call(call))
