# -*- coding: utf-8 -*-
"""Explicit, non-replaying SQLite transactions for an AnySQL connection."""
from contextlib import contextmanager
import sqlite3
import sys
import threading
from six import reraise


class SQLiteTransactions(object):
    """One transaction domain per strict AnySQL SQLite connection.

    The caller configures ``isolation_level=None`` and, when needed, WAL before
    use. Share ``lock`` with other operations on this connection. All transaction
    boundaries must go through this object; do not reconnect or manually commit
    inside its contexts. Nested contexts join the outer transaction, not a
    savepoint. A read snapshot is deferred, not SQL write protection: direct
    statements (including temporary tables) remain the caller's responsibility.
    """

    def __init__(self, connection):
        if connection.auto_reconnect:
            raise ValueError('SQLite transactions require auto_reconnect=False')
        driver = connection.driver_connection
        if not isinstance(driver, sqlite3.Connection):
            raise TypeError('SQLite transactions require a SQLite connection')
        if driver.isolation_level is not None:
            raise ValueError('SQLite transactions require isolation_level=None')
        self.connection = connection
        self.lock = threading.RLock()
        self._driver = driver
        self._active = False
        self._read_only = False
        self._failed = False

    def transaction(self):
        """Reserve a writer with BEGIN IMMEDIATE; commit or roll back once."""
        return self._transaction(False)

    def read_snapshot(self):
        """Begin a deferred snapshot without reserving the SQLite writer."""
        return self._transaction(True)

    @contextmanager
    def _transaction(self, read_only):
        with self.lock:
            if self._failed:
                raise RuntimeError('SQLite transaction domain requires a new connection')
            if (self.connection.driver_connection is not self._driver
                    or self._driver.isolation_level is not None):
                raise ValueError('SQLite transaction connection changed')
            if self._active:
                if not read_only and self._read_only:
                    raise ValueError('write_inside_read_snapshot')
                yield self.connection
                return
            # A failed BEGIN must not roll back a transaction owned elsewhere.
            self._driver.execute('BEGIN' if read_only else 'BEGIN IMMEDIATE')
            self._active = True
            self._read_only = read_only
            try:
                yield self.connection
                if self.connection.driver_connection is not self._driver:
                    raise ValueError('SQLite transaction connection changed')
                self._driver.execute('COMMIT')
            except BaseException:
                failure = sys.exc_info()
                try:
                    self._driver.execute('ROLLBACK')
                except Exception:
                    # Keep the original error and prevent reuse after uncertain
                    # cleanup. No reconnect, replay or second commit is allowed.
                    self._failed = True
                # Python 2 replaces the active exception after a nested except.
                # Preserve the original exception and traceback on every runtime.
                try:
                    reraise(*failure)
                finally:
                    del failure
            finally:
                self._active = False
                self._read_only = False
