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
