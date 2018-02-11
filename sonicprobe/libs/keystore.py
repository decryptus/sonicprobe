# -*- coding: utf-8 -*-
"""keystore"""

__author__  = "Adrien DELLE CAVE <adc@doowan.net>"
__license__ = """
    Copyright (C) 2017  doowan

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License along
    with this program; if not, write to the Free Software Foundation, Inc.,
    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA..
"""

import gc
import logging
import time
import threading

LOG = logging.getLogger('sonicprobe.keystore')


class Keystore(object):
    def __init__(self, timeout = 10):
        self.__data     = {}
        self.__lock     = {}
        self.__updated  = {}
        self.__me       = threading.RLock()
        self.__thread   = threading.currentThread()
        self.__locked   = None
        self.timeout    = timeout

    def _lock(self):
        already_locked = self.__locked
        if self.__locked and not self.try_lock(self.timeout):
            raise RuntimeError("unable to lock")

        return already_locked

    def _unlock(self, already_locked):
         if not already_locked and self.__locked == self.__thread:
            self.try_unlock()

    def add(self, name, lock = False):
        already_locked = self._lock()

        if not self.__data.has_key(name):
            self.__lock[name]       = threading.RLock()
            if lock:
                self.__lock[name].acquire()
            self.__data[name]       = {}
            self.__updated[name]    = 0
            if lock:
                self.__lock[name].release()

        self._unlock(already_locked)

        return self

    def get(self, name, key, default = None, lock = False):
        already_locked = self._lock()

        if not self.__lock.has_key(name):
            self._unlock(already_locked)
            return default

        if lock:
            self.__lock[name].acquire()
        r = self.__data[name].get(key, default)
        if lock:
            self.__lock[name].release()

        self._unlock(already_locked)

        return r

    def set(self, name, key, value = None, lock = False):
        already_locked = self._lock()

        if not self.__lock.has_key(name):
            self.add(name)
        if lock:
            self.__lock[name].acquire()
        self.__data[name][key]  = value
        self.__updated[name]    = time.time()
        if lock:
            self.__lock[name].release()

        self._unlock(already_locked)

        return self

    def exists(self, name, lock = False):
        already_locked = self._lock()

        if lock and self.__lock.has_key(name):
            self.__lock[name].acquire()

        r = self.__data.has_key(name)

        if lock and self.__lock.has_key(name):
            self.__lock[name].release()

        self._unlock(already_locked)

        return r

    def iteritems(self, name):
        already_locked = self._lock()

        for item in self.__data[name].items():
            yield item

        self._unlock(already_locked)

    def iterkeys(self, name):
        already_locked = self._lock()

        for key in self.__data[name].keys():
            yield key

        self._unlock(already_locked)

    def itervalues(self, name):
        already_locked = self._lock()

        for value in self.__data[name].values():
            yield value

        self._unlock(already_locked)

    def has_key(self, name, key, lock = False):
        already_locked = self._lock()

        if lock and self.__lock.has_key(name):
            self.__lock[name].acquire()

        r = self.__data[name].has_key(key)

        if lock and self.__lock.has_key(name):
            self.__lock[name].release()

        self._unlock(already_locked)

        return r

    def delete(self, name, lock = True):
        already_locked = self._lock()

        if lock and self.__lock.has_key(name):
            self.__lock[name].acquire()

        if self.__data.has_key(name):
            del self.__data[name]
        if self.__updated.has_key(name):
            del self.__updated[name]

        if lock and self.__lock.has_key(name):
            self.__lock[name].release()

        if self.__lock.has_key(name):
            del self.__lock[name]

        self._unlock(already_locked)
        gc.collect()

        return self

    def remove(self, name, key, lock = False):
        already_locked = self._lock()

        if lock:
            self.__lock[name].acquire()
        if self.__data.has_key(key):
            del self.__data[name][key]
        self.__updated[name] = time.time()
        if lock:
            self.__lock[name].release()

        self._unlock(already_locked)

        return self

    def updated_at(self, name, default = None, lock = False):
        already_locked = self._lock()

        if lock and self.__lock.has_key(name):
            self.__lock[name].acquire()
        r = self.__updated.get(name, default)
        if lock and self.__lock.has_key(name):
            self.__lock[name].release()

        self._unlock(already_locked)

        return r

    def updated_delta(self, name, lock = False):
        already_locked = self._lock()

        if lock and self.__lock.has_key(name):
            self.__lock[name].acquire()
        r = time.time() - self.__updated[name]
        if lock and self.__lock.has_key(name):
            self.__lock[name].release()

        self._unlock(already_locked)

        return r

    def expired(self, name, expire, lock = False):
        already_locked = self._lock()

        if lock and self.__lock.has_key(name):
            self.__lock[name].acquire()

        try:
            if not self.__updated.has_key(name):
                return None
            elif expire < 0:
                return False
            return self.updated_delta(name) > expire
        finally:
            if lock and self.__lock.has_key(name):
                self.__lock[name].release()
            self._unlock(already_locked)

    def purge(self, name, lock = False):
        already_locked = self._lock()

        if lock and self.__lock.has_key(name):
            self.__lock[name].acquire()

        if self.__data.has_key(name):
            self.__data[name]       = {}
        if self.__updated.has_key(name):
            self.__updated[name]    = 0

        if lock and self.__lock.has_key(name):
            self.__lock[name].release()

        self._unlock(already_locked)

        return self

    def reset(self, name, lock = False):
        already_locked = self._lock()

        if lock and self.__lock.has_key(name):
            self.__lock[name].acquire()

        if self.__data.has_key(name):
            self.__data[name]       = {}
        if self.__updated.has_key(name):
            self.__updated[name]    = time.time()

        if lock and self.__lock.has_key(name):
            self.__lock[name].release()

        self._unlock(already_locked)

        return self

    def acquire(self, name, blocking = True, lock = True, exists = False):
        already_locked = self._lock()

        if not exists:
            self.add(name, lock)
        elif not self.exists(name, lock):
            return None

        try:
            return self.__lock[name].acquire(blocking)
        except KeyError:
            if not exists:
                raise
            return None
        finally:
            self._unlock(already_locked)

    def try_acquire(self, name, timeout = None, exists = False):
        already_locked = self._lock()

        if timeout is not None:
            endtime = time.time() + timeout

        if not exists:
            self.add(name, False)
        elif not self.exists(name, False):
            return None

        try:
            while True:
                if not self.__lock.has_key(name):
                    return None
                elif self.__lock[name].acquire(False):
                    return True
                elif timeout is not None:
                    remaining = endtime - time.time()
                    if remaining <= 0:
                        return 0
                else:
                    return False
        except KeyError:
            if not exists:
                raise
            return None
        finally:
            self._unlock(already_locked)

    def release(self, name):
        if self.__lock.has_key(name):
            self.__lock[name].release()
        return self

    def try_release(self, name):
        try:
            self.release(name)
        except (KeyError, RuntimeError):
            pass

        return self

    def list(self):
        already_locked = self._lock()

        r = self.__data.keys()

        self._unlock(already_locked)

        return r

    def lock(self, blocking = True):
        if self.__me.acquire(blocking):
            self.__locked = threading.currentThread()
            return True

    def try_lock(self, timeout = None):
        if timeout is not None:
            endtime = time.time() + timeout

        while True:
            if self.__me.acquire(False):
                self.__locked = threading.currentThread()
                return True
            elif timeout is not None:
                remaining = endtime - time.time()
                if remaining <= 0:
                    return 0
            else:
                return False

    def try_unlock(self):
        try:
            self.__locked = self.__me.release()
        except RuntimeError:
            pass

        return self

    def unlock(self):
        self.__locked = self.__me.release()

        return self
