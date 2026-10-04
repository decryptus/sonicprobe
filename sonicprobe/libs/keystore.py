# -*- coding: utf-8 -*-
# Copyright (C) 2015-2019 Adrien Delle Cave
# SPDX-License-Identifier: GPL-3.0-or-later
"""Named memory sections with reentrant section and global ownership."""

from contextlib import contextmanager
import gc
import logging
import threading
import time

LOG = logging.getLogger('sonicprobe.keystore')
_clock = getattr(time, 'monotonic', time.time)
LOCK_RETRY_INTERVAL = 0.01


class Keystore(object):
    def __init__(self, timeout=10):
        self.__data = {}
        self.__lock = {}
        self.__updated = {}
        self.__owners = {}
        self.__waiters = {}
        self.__condition = threading.Condition(threading.RLock())
        self.__global_owner = None
        self.__global_depth = 0
        self.__global_waiters = 0
        self.timeout = timeout

    @staticmethod
    def _deadline(timeout):
        return None if timeout is None else _clock() + timeout

    def _wait(self, deadline):
        remaining = None if deadline is None else deadline - _clock()
        if remaining is not None and remaining <= 0:
            return False
        self.__condition.wait(remaining)
        return True

    def _owns_section(self, thread):
        return any(owner[0] is thread for owner in self.__owners.values())

    def _can_enter(self, thread):
        if self.__global_owner is not None:
            return self.__global_owner is thread
        return not self.__global_waiters or self._owns_section(thread)

    def _enter(self, deadline, global_request=False):
        # Python 2 RLock has no timed acquire. Include mutex contention in the
        # timeout rather than blocking before the advertised deadline starts.
        while not self.__condition.acquire(False):
            remaining = None if deadline is None else deadline - _clock()
            if remaining is not None and remaining <= 0:
                return False
            time.sleep(LOCK_RETRY_INTERVAL if remaining is None else
                       min(LOCK_RETRY_INTERVAL, remaining))
        try:
            me = threading.current_thread()
            while ((self.__global_owner is not None and self.__global_owner is not me)
                   or (not global_request and not self._can_enter(me))):
                if not self._wait(deadline):
                    self.__condition.release()
                    return False
            return True
        except BaseException:
            self.__condition.release()
            raise

    def _lock(self):
        if not self._enter(self._deadline(self.timeout)):
            raise RuntimeError('unable to lock')
        return False

    def _unlock(self, already_locked):
        if not already_locked:
            self.__condition.release()

    @contextmanager
    def _guard(self):
        acquired = self._lock()
        try:
            yield
        finally:
            self._unlock(acquired)

    def _ensure_lock(self, name):
        if name not in self.__lock:
            self.__lock[name] = threading.RLock()
        return self.__lock[name]

    def _ensure_data(self, name):
        if name not in self.__data:
            self.__data[name] = {}
            self.__updated[name] = 0

    def _cleanup_section(self, name):
        # A deleted section retains its lock until its last owner/waiter leaves.
        if (name not in self.__data and name not in self.__owners
                and not self.__waiters.get(name, 0)):
            self.__lock.pop(name, None)
            self.__waiters.pop(name, None)

    def _acquire_section(self, name, deadline, exists=False):
        section_lock = self._ensure_lock(name)
        self.__waiters[name] = self.__waiters.get(name, 0) + 1
        me = threading.current_thread()
        try:
            while True:
                if exists and name not in self.__data:
                    return None
                if self._can_enter(me):
                    if section_lock.acquire(False):
                        owner = self.__owners.get(name)
                        self.__owners[name] = [me, 1 if owner is None else owner[1] + 1]
                        return True
                if not self._wait(deadline):
                    return False
        finally:
            self.__waiters[name] -= 1
            self._cleanup_section(name)

    def _release_section(self, name):
        owner = self.__owners.get(name)
        if owner is None or owner[0] is not threading.current_thread():
            raise RuntimeError('cannot release an unowned section lock')
        self.__lock[name].release()
        owner[1] -= 1
        if not owner[1]:
            del self.__owners[name]
        self._cleanup_section(name)
        self.__condition.notify_all()

    @contextmanager
    def _section_guard(self, name, enabled, missing_ok=True, create=False):
        acquired = False
        if not missing_ok and name not in self.__data:
            raise KeyError(name)
        try:
            if create:
                self._ensure_lock(name)
            if enabled and name in self.__lock:
                acquired = self._acquire_section(name, None)
            if create:
                self._ensure_data(name)
            yield
        finally:
            if acquired:
                self._release_section(name)
            else:
                self._cleanup_section(name)

    def add(self, name, lock=False):
        with self._guard(), self._section_guard(name, lock, create=True):
            pass
        return self

    def get(self, name, key, default=None, lock=False):
        with self._guard(), self._section_guard(name, lock):
            section = self.__data.get(name)
            return default if section is None else section.get(key, default)

    def set(self, name, key, value=None, lock=False):
        with self._guard(), self._section_guard(name, lock, create=True):
            self.__data[name][key] = value
            self.__updated[name] = time.time()
        return self

    def exists(self, name, lock=False):
        with self._guard(), self._section_guard(name, lock):
            return name in self.__data

    def iteritems(self, name):
        with self._guard():
            return iter(list(self.__data[name].items()))

    def iterkeys(self, name):
        with self._guard():
            return iter(list(self.__data[name].keys()))

    def itervalues(self, name):
        with self._guard():
            return iter(list(self.__data[name].values()))

    def has_key(self, name, key, lock=False):
        with self._guard(), self._section_guard(name, lock):
            return key in self.__data[name]

    def delete(self, name, lock=True):
        with self._guard(), self._section_guard(name, lock):
            self.__data.pop(name, None)
            self.__updated.pop(name, None)
            self.__condition.notify_all()
        gc.collect()
        return self

    def remove(self, name, key, lock=False):
        with self._guard(), self._section_guard(name, lock, missing_ok=False):
            # A concurrent delete may have completed while waiting for the lock.
            section = self.__data[name]
            section.pop(key, None)
            self.__updated[name] = time.time()
        return self

    def updated_at(self, name, default=None, lock=False):
        with self._guard(), self._section_guard(name, lock):
            return self.__updated.get(name, default)

    def updated_delta(self, name, lock=False):
        with self._guard(), self._section_guard(name, lock):
            return time.time() - self.__updated[name]

    def expired(self, name, expire, lock=False):
        with self._guard(), self._section_guard(name, lock):
            if name not in self.__updated:
                return None
            if expire < 0:
                return False
            return time.time() - self.__updated[name] > expire

    def purge(self, name, lock=False):
        with self._guard(), self._section_guard(name, lock):
            if name in self.__data:
                self.__data[name] = {}
                self.__updated[name] = 0
        return self

    def reset(self, name, lock=False):
        with self._guard(), self._section_guard(name, lock):
            if name in self.__data:
                self.__data[name] = {}
                self.__updated[name] = time.time()
        return self

    def _acquire_named(self, name, deadline, exists, failure, blocking_entry=False):
        entry_deadline = self._deadline(self.timeout) if blocking_entry else deadline
        if not self._enter(entry_deadline):
            if blocking_entry:
                raise RuntimeError('unable to lock')
            return failure
        try:
            if exists and name not in self.__data:
                return None
            acquired = self._acquire_section(name, deadline, exists)
            if acquired:
                try:
                    if not exists:
                        self._ensure_data(name)
                except BaseException:
                    self._release_section(name)
                    raise
                return True
            return None if acquired is None else failure
        finally:
            self.__condition.release()

    def acquire(self, name, blocking=True, lock=True, exists=False):
        # lock is retained as a compatibility parameter; existence checks never
        # perform a separate blocking section acquisition.
        if not blocking:
            hash(name)
        return self._acquire_named(name, None if blocking else self._deadline(0),
                                   exists, False, blocking_entry=blocking)

    def try_acquire(self, name, timeout=None, exists=False):
        hash(name)
        return self._acquire_named(name, self._deadline(0 if timeout is None else timeout),
                                   exists, False if timeout is None else 0)

    def release(self, name):
        # Releasing ownership must remain possible while other threads wait.
        with self.__condition:
            if name in self.__lock:
                self._release_section(name)
        return self

    def try_release(self, name):
        try:
            self.release(name)
        except (KeyError, RuntimeError):
            pass
        return self

    def list(self):
        with self._guard():
            return list(self.__data.keys())

    def _acquire_global(self, deadline):
        if not self._enter(deadline, global_request=True):
            return False
        self.__global_waiters += 1
        try:
            me = threading.current_thread()
            while True:
                owners = [owner[0] for owner in self.__owners.values()]
                if ((self.__global_owner is None or self.__global_owner is me)
                        and all(owner is me for owner in owners)):
                    self.__global_owner = me
                    self.__global_depth += 1
                    return True
                # Two section owners must not wait on each other while both
                # attempt to promote to global ownership. No locks are lost.
                if me in owners or not self._wait(deadline):
                    return False
        finally:
            self.__global_waiters -= 1
            self.__condition.notify_all()
            self.__condition.release()

    def lock(self, blocking=True):
        return True if self._acquire_global(None if blocking else self._deadline(0)) else None

    def try_lock(self, timeout=None):
        if self._acquire_global(self._deadline(0 if timeout is None else timeout)):
            return True
        return False if timeout is None else 0

    def try_unlock(self):
        try:
            self.unlock()
        except RuntimeError:
            pass
        return self

    def unlock(self):
        with self.__condition:
            if self.__global_owner is not threading.current_thread():
                raise RuntimeError('cannot release an unowned lock')
            self.__global_depth -= 1
            if not self.__global_depth:
                self.__global_owner = None
                self.__condition.notify_all()
        return self
