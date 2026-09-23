# -*- coding: utf-8 -*-
# Copyright (C) 2015-2019 Adrien Delle Cave
# SPDX-License-Identifier: GPL-3.0-or-later
"""sonicprobe.libs.keystore"""

from contextlib import contextmanager
import gc
import logging
import time

from sonicprobe.libs.moresynchro import RWLock
import threading

LOG = logging.getLogger('sonicprobe.keystore')


class Keystore(object): # pylint: disable=useless-object-inheritance
    def __init__(self, timeout = 10):
        self.__data     = {}
        self.__lock     = {}
        self.__updated  = {}
        self.__gate     = RWLock()
        self.__explicit = threading.local()
        self.__creation = threading.Lock()
        self.timeout    = timeout

    def _lock(self):
        # Ordinary operations hold a shared gate for their full lifetime.
        # Explicit global locks take the exclusive side of the same gate.
        if not self.__gate.acquire_read(self.timeout):
            raise RuntimeError('unable to lock')
        return False

    def _unlock(self, already_locked):
        if not already_locked:
            self.__gate.release()

    @contextmanager
    def _guard(self):
        # Each operation balances its shared acquisition, including nested
        # calls made by the owner of an explicit exclusive lock.
        already_locked = self._lock()
        try:
            yield
        finally:
            self._unlock(already_locked)

    @contextmanager
    def _section_guard(self, name, enabled, missing_ok = True):
        section_lock = None
        if enabled:
            section_lock = (self.__lock.get(name) if missing_ok else self.__lock[name])
        if section_lock is not None:
            section_lock.acquire()
        try:
            yield
        finally:
            # Keep the acquired object even if the section is deleted.
            if section_lock is not None:
                section_lock.release()

    def add(self, name, lock = False):
        with self._guard(), self.__creation:
            if name not in self.__data:
                self.__lock[name] = threading.RLock()
                with self._section_guard(name, lock):
                    self.__data[name] = {}
                    self.__updated[name] = 0
        return self

    def get(self, name, key, default = None, lock = False):
        with self._guard():
            if name not in self.__lock:
                return default
            with self._section_guard(name, lock):
                return self.__data[name].get(key, default)

    def set(self, name, key, value = None, lock = False):
        with self._guard():
            if name not in self.__lock:
                self.add(name)
            with self._section_guard(name, lock):
                self.__data[name][key] = value
                self.__updated[name] = time.time()
        return self

    def exists(self, name, lock = False):
        with self._guard(), self._section_guard(name, lock):
            return name in self.__data

    def iteritems(self, name):
        with self._guard():
            snapshot = list(self.__data[name].items())
        return iter(snapshot)

    def iterkeys(self, name):
        with self._guard():
            snapshot = list(self.__data[name].keys())
        return iter(snapshot)

    def itervalues(self, name):
        with self._guard():
            snapshot = list(self.__data[name].values())
        return iter(snapshot)

    def has_key(self, name, key, lock = False):
        with self._guard(), self._section_guard(name, lock):
            return key in self.__data[name]

    def delete(self, name, lock = True):
        with self._guard():
            with self._section_guard(name, lock):
                if name in self.__data:
                    del self.__data[name]
                if name in self.__updated:
                    del self.__updated[name]
            if name in self.__lock:
                del self.__lock[name]
        gc.collect()
        return self

    def remove(self, name, key, lock = False):
        with self._guard(), self._section_guard(name, lock, missing_ok=False):
            if name in self.__data and key in self.__data[name]:
                del self.__data[name][key]
            self.__updated[name] = time.time()
        return self

    def updated_at(self, name, default = None, lock = False):
        with self._guard(), self._section_guard(name, lock):
            return self.__updated.get(name, default)

    def updated_delta(self, name, lock = False):
        with self._guard(), self._section_guard(name, lock):
            return time.time() - self.__updated[name]

    def expired(self, name, expire, lock = False):
        with self._guard(), self._section_guard(name, lock):
            if name not in self.__updated:
                return None
            if expire < 0:
                return False
            return self.updated_delta(name) > expire

    def purge(self, name, lock = False):
        with self._guard(), self._section_guard(name, lock):
            if name in self.__data:
                self.__data[name] = {}
            if name in self.__updated:
                self.__updated[name] = 0
        return self

    def reset(self, name, lock = False):
        with self._guard(), self._section_guard(name, lock):
            if name in self.__data:
                self.__data[name] = {}
            if name in self.__updated:
                self.__updated[name] = time.time()
        return self

    def acquire(self, name, blocking = True, lock = True, exists = False):
        with self._guard():
            if not exists:
                self.add(name, lock)
            elif not self.exists(name, lock):
                return None
            try:
                # The caller owns this section lock until release(name).
                return self.__lock[name].acquire(blocking)
            except KeyError:
                if not exists:
                    raise
                return None

    def try_acquire(self, name, timeout = None, exists = False):
        with self._guard():
            if timeout is not None:
                endtime = time.time() + timeout
            if not exists:
                self.add(name, False)
            elif not self.exists(name, False):
                return None
            try:
                while True:
                    if name not in self.__lock:
                        return None
                    if self.__lock[name].acquire(False):
                        return True
                    if timeout is None:
                        return False
                    remaining = endtime - time.time()
                    if remaining <= 0:
                        return 0
                    time.sleep(min(0.01, remaining))
            except KeyError:
                if not exists:
                    raise
                return None

    def release(self, name):
        if name in self.__lock:
            self.__lock[name].release()
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

    def lock(self, blocking = True):
        if self.__gate.acquire_write(None if blocking else 0):
            self.__explicit.depth = getattr(self.__explicit, 'depth', 0) + 1
            return True
        return None

    def try_lock(self, timeout = None):
        if self.__gate.acquire_write(0 if timeout is None else timeout):
            self.__explicit.depth = getattr(self.__explicit, 'depth', 0) + 1
            return True
        return False if timeout is None else 0

    def try_unlock(self):
        try:
            self.unlock()
        except RuntimeError:
            pass
        return self

    def unlock(self):
        depth = getattr(self.__explicit, 'depth', 0)
        if not depth:
            raise RuntimeError('cannot release an unowned lock')
        self.__gate.release()
        self.__explicit.depth = depth - 1
        return self
