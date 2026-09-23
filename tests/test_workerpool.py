import threading
import time
import unittest
from six.moves import queue
from sonicprobe.libs.workerpool import WorkerPool


class WorkerPoolTests(unittest.TestCase):
    def pool(self, **kwargs):
        pool = WorkerPool(auto_gc=False, **kwargs)
        self.addCleanup(pool.killall, 2)
        return pool

    def test_positional_arguments_and_callbacks(self):
        result, completed = [], threading.Event()
        pool = self.pool(max_workers=1)
        pool.run(lambda a, b: a + b, result.append, None,
                 lambda value: completed.set(), None, 2, 3)
        self.assertTrue(completed.wait(3))
        self.assertEqual(result, [5])

    def test_completion_error_does_not_strand_worker_or_queue(self):
        pool = self.pool(max_workers=1)
        done = threading.Event()
        def broken(value):
            raise ValueError('expected test failure')
        pool.run(lambda: 1, complete=broken)
        pool.run(done.set)
        self.assertTrue(done.wait(3))
        pool.killall(3)
        self.assertEqual(pool.count_working(), 0)
        self.assertEqual(pool.tasks.unfinished_tasks, 0)

    def test_equal_priorities_are_fifo(self):
        pool = self.pool(queue=queue.PriorityQueue(), max_workers=1)
        started, release, done = threading.Event(), threading.Event(), threading.Event()
        result = []
        def block():
            started.set()
            release.wait(3)
        pool.run(block)
        self.assertTrue(started.wait(3))
        pool.run_args(result.append, 'first', _qpriority_=1)
        pool.run_args(result.append, 'second', _qpriority_=1, _complete_=lambda value: done.set())
        release.set()
        self.assertTrue(done.wait(3))
        self.assertEqual(result, ['first', 'second'])

    def test_worker_recycling(self):
        pool = self.pool(max_workers=1, max_tasks=1)
        done, result = threading.Event(), []
        for n in range(8):
            pool.run_args(result.append, n)
        pool.run(done.set)
        self.assertTrue(done.wait(3))
        self.assertEqual(result, list(range(8)))

    def test_stopped_pool_rejects_submission(self):
        pool = self.pool()
        pool.killall(1)
        with self.assertRaises(RuntimeError):
            pool.run(lambda: None)

    def test_idle_worker_uses_blocking_queue_get(self):
        class TrackingQueue(queue.Queue):
            def __init__(self):
                queue.Queue.__init__(self)
                self.called = threading.Event()
                self.timeouts = []
            def get(self, block=True, timeout=None):
                self.timeouts.append(timeout)
                self.called.set()
                return queue.Queue.get(self, block, timeout)
        tasks = TrackingQueue()
        pool = self.pool(queue=tasks)
        pool.add()
        self.assertTrue(tasks.called.wait(3))
        self.assertEqual(tasks.timeouts[0], 0.1)
        pool.killall(3)
        self.assertEqual(pool.count_workers(), 0)

    def test_failed_thread_start_rolls_back_and_allows_retry(self):
        try:
            from unittest import mock
        except ImportError:
            import mock
        pool = self.pool(max_workers=1)
        with mock.patch('sonicprobe.libs.workerpool.WorkerThread.start',
                        side_effect=RuntimeError('cannot start thread')):
            with self.assertRaises(RuntimeError):
                pool.run(lambda: None)
        self.assertEqual(pool.count_workers(), 0)
        self.assertEqual(pool.tasks.unfinished_tasks, 0)
        self.assertTrue(pool.kill_event.is_set())
        done = threading.Event()
        pool.run(done.set)
        self.assertTrue(done.wait(2))

    def test_bounded_queue_does_not_hold_bookkeeping_lock_while_full(self):
        pool = self.pool(queue=queue.Queue(1), max_workers=1)
        started, release, done = threading.Event(), threading.Event(), threading.Event()
        result = []
        def block():
            started.set()
            release.wait(3)
        pool.run(block)
        self.assertTrue(started.wait(2))
        pool.run_args(result.append, 1)
        producer = threading.Thread(target=lambda: pool.run(done.set))
        producer.daemon = True
        producer.start()
        release.set()
        producer.join(2)
        self.assertFalse(producer.is_alive())
        self.assertTrue(done.wait(2))
        self.assertEqual(result, [1])

    def test_stop_rejects_a_producer_waiting_on_a_full_queue(self):
        pool = self.pool(queue=queue.Queue(1), max_workers=1)
        started, release = threading.Event(), threading.Event()
        result = []
        def block():
            started.set()
            release.wait(3)
        pool.run(block)
        self.assertTrue(started.wait(2))
        pool.run(lambda: None)
        def submit():
            try:
                pool.run(lambda: None)
            except RuntimeError:
                result.append('stopped')
        producer = threading.Thread(target=submit)
        producer.daemon = True
        producer.start()
        try:
            pool.killall(0)
        finally:
            release.set()
        producer.join(2)
        pool.killall(2)
        self.assertFalse(producer.is_alive())
        self.assertEqual(result, ['stopped'])
        self.assertEqual(pool.tasks.unfinished_tasks, 0)
        self.assertEqual(pool.count_workers(), 0)

    def test_killable_includes_task_between_dequeue_and_execution(self):
        class HandoffQueue(queue.Queue):
            def __init__(self):
                queue.Queue.__init__(self)
                self.taken, self.resume = threading.Event(), threading.Event()
            def get(self, block=True, timeout=None):
                task = queue.Queue.get(self, block, timeout)
                self.taken.set()
                self.resume.wait(3)
                return task
        tasks = HandoffQueue()
        pool = self.pool(queue=tasks, max_workers=1)
        done = threading.Event()
        pool.run(done.set)
        try:
            self.assertTrue(tasks.taken.wait(2))
            self.assertFalse(pool.killable())
        finally:
            tasks.resume.set()
        self.assertTrue(done.wait(2))
        pool.tasks.join()
        self.assertTrue(pool.killable())

    def test_worker_cannot_wait_for_its_own_shutdown(self):
        pool = self.pool(max_workers=1)
        done, errors = threading.Event(), []
        def stop():
            try:
                pool.killall()
            except RuntimeError:
                errors.append('rejected')
            finally:
                done.set()
        pool.run(stop)
        self.assertTrue(done.wait(2))
        self.assertEqual(errors, ['rejected'])
        self.assertFalse(pool.exit)

    def test_growth_failure_does_not_drop_the_current_task(self):
        try:
            from unittest import mock
        except ImportError:
            import mock
        pool = self.pool(max_workers=2)
        pool.add()
        done = threading.Event()
        with mock.patch.object(pool, 'add', side_effect=RuntimeError('cannot grow')):
            pool.run(done.set)
            self.assertTrue(done.wait(2))
            pool.tasks.join()
        self.assertEqual(pool.count_working(), 0)

    def test_stopped_pool_cannot_start_new_workers(self):
        pool = self.pool()
        pool.killall(1)
        with self.assertRaises(RuntimeError):
            pool.add()
        self.assertEqual(pool.count_workers(), 0)

    def test_concurrent_producers_and_recycling_execute_each_task_once(self):
        pool = self.pool(max_workers=4, max_tasks=3)
        done, result_lock = threading.Event(), threading.Lock()
        received = []
        def record(value):
            with result_lock:
                received.append(value)
                if len(received) == 120:
                    done.set()
        def produce(offset):
            for value in range(offset, offset + 30):
                pool.run_args(record, value)
        producers = [threading.Thread(target=produce, args=(i * 30,)) for i in range(4)]
        for thread in producers:
            thread.start()
        for thread in producers:
            thread.join(3)
            self.assertFalse(thread.is_alive())
        self.assertTrue(done.wait(5))
        pool.tasks.join()
        self.assertEqual(sorted(received), list(range(120)))
        pool.killall(3)
        self.assertEqual(pool.count_workers(), 0)
        self.assertEqual(pool.count_working(), 0)
        self.assertEqual(pool.tasks.unfinished_tasks, 0)

    def test_base_exception_retires_worker_and_acknowledges_task(self):
        try:
            from unittest import mock
        except ImportError:
            import mock
        from sonicprobe.libs.workerpool import WorkerThread
        original = WorkerThread.run
        def quiet_run(worker):
            try:
                original(worker)
            except KeyboardInterrupt:
                pass
        pool = self.pool(max_workers=1)
        attempted, done = threading.Event(), threading.Event()
        def interrupted():
            raise KeyboardInterrupt()
        with mock.patch.object(WorkerThread, 'run', quiet_run):
            pool.run(interrupted, complete=lambda value: attempted.set())
            self.assertTrue(attempted.wait(2))
            pool.run(done.set)
            self.assertTrue(done.wait(2))
            pool.tasks.join()
            pool.killall(2)
        self.assertEqual(pool.count_workers(), 0)
        self.assertEqual(pool.count_working(), 0)
        self.assertEqual(pool.tasks.unfinished_tasks, 0)
