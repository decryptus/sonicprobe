# -*- coding: utf-8 -*-
# Copyright (C) 2015-2019 Adrien Delle Cave
# SPDX-License-Identifier: GPL-3.0-or-later
"""sonicprobe.libs.workerpool"""

import gc
import itertools
import logging
import threading
import time

from six.moves import queue as _queue, range as xrange

from sonicprobe import helpers

LOG = logging.getLogger('sonicprobe.workerpool')

DEFAULT_MAX_WORKERS   = 10
DEFAULT_EXIT_PRIORITY = -9999

_clock = getattr(time, 'monotonic', time.time)


class WorkerExit(object): # pylint: disable=useless-object-inheritance,too-few-public-methods
    pass


class WorkerThread(threading.Thread):
    def __init__(self, xid, pool):
        threading.Thread.__init__(self)
        self.daemon     = True
        self.pool       = pool
        self.life_time  = None
        self.nb_tasks   = None
        self.xid        = xid

    def start(self):
        self.nb_tasks   = 0
        self.life_time  = _clock()
        return threading.Thread.start(self)

    def expired(self):
        if self.pool.life_time \
           and self.pool.life_time > 0 \
           and self.life_time > 0 \
           and (_clock() - self.life_time) >= self.pool.life_time:
            LOG.debug("worker expired")
            return True

        return False

    def max_tasks_reached(self):
        if self.pool.max_tasks \
           and self.pool.max_tasks > 0 \
           and self.nb_tasks > 0 \
           and self.nb_tasks >= self.pool.max_tasks:
            LOG.debug("worker max tasks reached")
            return True

        return False

    def run(self):
        name = None
        try:
            while not self.pool.exit:
                if self.expired() or self.max_tasks_reached():
                    if self.pool.auto_gc:
                        gc.collect()
                    break
                try:
                    entry = self.pool.tasks.get(timeout=0.1)
                except _queue.Empty:
                    continue
                working = False
                try:
                    task = entry[-1] if self.pool.is_qpriority else entry
                    with self.pool.count_lock:
                        if self.pool.exit or isinstance(task, WorkerExit):
                            break
                        self.pool.working += 1
                        working = True
                        grow = ((not self.pool.tasks.empty()
                                 or self.pool.working >= self.pool.workers)
                                and self.pool.workers < self.pool.max_workers)
                    if grow:
                        try:
                            self.pool.add()
                        except Exception:
                            LOG.exception('unable to grow worker pool')
                    func, cb, name, complete, args, kargs = task
                    self.name = self.pool.get_name(self.xid, name)
                    ret = None
                    try:
                        self.nb_tasks += 1
                        ret = func(*args, **kargs)
                        if cb:
                            cb(ret)
                    except (Exception, SystemExit) as error:
                        LOG.exception('unexpected worker error: %r', error)
                    finally:
                        try:
                            if complete:
                                complete(ret)
                        except (Exception, SystemExit) as error:
                            LOG.exception('completion callback failed: %r', error)
                finally:
                    # Even BaseException and setup errors must acknowledge the
                    # dequeued item and retire this worker's accounting.
                    with self.pool.count_lock:
                        if working:
                            self.pool.working -= 1
                        self.pool.tasks.task_done()
        finally:
            with self.pool.count_lock:
                self.pool.workers -= 1
                self.pool.id_list.append(self.xid)
                if not self.pool.exit and not self.pool.tasks.empty():
                    try:
                        self.pool.add(name=name)
                    except Exception:
                        LOG.exception('unable to replace worker')
                if not self.pool.workers:
                    self.pool.kill_event.set()


class WorkerPool(object): # pylint: disable=useless-object-inheritance
    def __init__(self, queue = None, max_workers = DEFAULT_MAX_WORKERS, life_time = None, name = None, max_tasks = None, auto_gc = True):
        self.tasks        = queue or _queue.Queue()
        self.workers      = 0
        self.working      = 0
        self.max_workers  = helpers.get_nb_workers(max_workers, xmin = 1, default = DEFAULT_MAX_WORKERS)
        self.life_time    = life_time
        self.name         = name
        self.max_tasks    = max_tasks
        self.auto_gc      = auto_gc
        self.id_list      = []
        self.sequence     = itertools.count()
        self.worker_ids   = itertools.count(1)

        self.exit         = False
        self.kill_event   = threading.Event()
        self.count_lock   = threading.RLock()

        self.is_qpriority = isinstance(self.tasks, _queue.PriorityQueue)

        self.kill_event.set()

    def count_workers(self):
        with self.count_lock:
            return self.workers

    def count_working(self):
        with self.count_lock:
            return self.working

    def killable(self):
        # Includes a dequeued item whose worker has not yet incremented working.
        with self.tasks.all_tasks_done:
            return self.tasks.unfinished_tasks == 0

    def kill(self, nb = 1):
        """Ask up to nb workers to exit after their current task."""
        with self.count_lock:
            nb = min(int(nb), self.workers)
        for _ in xrange(max(0, nb)):
            task = WorkerExit()
            if self.is_qpriority:
                task = (DEFAULT_EXIT_PRIORITY, next(self.sequence), task)
            if not self._put(task, stopping=True):
                return

    def set_max_workers(self, nb):
        nb = int(nb)
        if nb < 1:
            raise ValueError('max_workers must be positive')
        with self.count_lock:
            self.max_workers = nb
            excess = max(0, self.workers - nb)
        # A bounded queue may wait here; never retain count_lock while waiting.
        self.kill(excess)

    def get_max_workers(self):
        return self.max_workers

    def get_name(self, xid, name = None):
        if name:
            return "%s:%d" % (name, xid)

        if self.name:
            return "%s:%d" % (self.name, xid)

        return "wpool:%d" % xid

    def add(self, nb = 1, name = None, xid = None):
        """Create workers, rolling back bookkeeping if startup fails."""
        nb = max(1, int(nb))
        with self.count_lock:
            if self.exit:
                raise RuntimeError('Cannot add workers to a stopped pool')
            for _ in xrange(min(nb, self.max_workers)):
                if self.workers >= self.max_workers:
                    break
                worker_id = xid
                xid = None
                if worker_id is None:
                    worker_id = (self.id_list.pop(0) if self.id_list
                                 else next(self.worker_ids))
                worker = WorkerThread(worker_id, self)
                worker.name = self.get_name(worker_id, name)
                self.workers += 1
                self.kill_event.clear()
                try:
                    worker.start()
                except BaseException:
                    self.workers -= 1
                    self.id_list.append(worker_id)
                    if not self.workers:
                        self.kill_event.set()
                    raise

    def _put(self, task, stopping=False, name=None):
        while True:
            with self.count_lock:
                if self.exit:
                    if stopping:
                        return False
                    raise RuntimeError('Cannot submit work to a stopped pool')
                if not stopping and not self.workers:
                    # Start before enqueueing so failure cannot leave a phantom
                    # accepted task with no worker to execute it.
                    self.add(name=name)
                try:
                    self.tasks.put_nowait(task)
                    return True
                except _queue.Full:
                    pass
            # Release the bookkeeping lock while applying backpressure.
            time.sleep(0.01)

    def _run(self, target, _callback_ = None, _name_ = None, _complete_ = None, _qpriority_ = None, *args, **kwargs):
        task = (target, _callback_, _name_, _complete_, args, kwargs)
        if self.is_qpriority:
            priority = time.time() if _qpriority_ is None else _qpriority_
            task = (priority, next(self.sequence), task)
        self._put(task, name=_name_)

    def run(self, target, callback = None, name = None, complete = None, qpriority = None, *args, **kargs):
        """
        Start task.
        @target: callable to run with *args and **kargs arguments.
        @callback: callable executed after target.
        @name: thread name
        @complete: complete executed after target in finally
        @qpriority: priority for PriorityQueue
        """
        self._run(target, callback, name, complete, qpriority, *args, **kargs)

    def run_args(self, target, *args, **kwargs):
        self._run(target, kwargs.pop('_callback_', None),
                  kwargs.pop('_name_', None), kwargs.pop('_complete_', None),
                  kwargs.pop('_qpriority_', None), *args, **kwargs)

    def killall(self, wait = None):
        """
        Kill all active workers.
        @wait: Seconds to wait until last worker ends.
               If None it waits forever.
        """
        if (getattr(threading.current_thread(), 'pool', None) is self
                and (wait is None or wait > 0)):
            raise RuntimeError('A worker cannot wait for its own pool to stop')
        with self.count_lock:
            self.exit = True
            while True:
                try:
                    self.tasks.get_nowait()
                except _queue.Empty:
                    break
                else:
                    self.tasks.task_done()
        self.kill_event.wait(wait)
