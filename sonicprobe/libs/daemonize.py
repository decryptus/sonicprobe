# -*- coding: utf-8 -*-
# Copyright 2007-2019 The Wazo Authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""sonicprobe.libs.daemonize"""

"""Transforms a process into a daemon from hell

WARNING: Linux specific module, needs /proc/
"""

import os
import re
import sys
import errno
import logging
from contextlib import contextmanager

SLASH_PROC = os.sep + 'proc'
PROG_SLINK = 'exe'
PROG_CMDLN = 'cmdline'


LOG = logging.getLogger(__name__)  # pylint: disable-msg=C0103


def c14n_prog_name(arg):
    return os.path.basename(re.sub(r'\.py$', '', arg))


def remove_if_stale_pidfile(pidfile):
    """
    @pidfile: PID file to remove if it is staled.

    Exceptions are logged and are not propagated.
    """
    try:
        try:
            with open(pidfile) as stream:
                pid_maydaemon = int(stream.readline().strip())
        except IOError as e:
            if e.errno == errno.ENOENT:
                return  # nothing to suppress, so do nothing...
            raise
        # Who are we?
        i_am = c14n_prog_name(sys.argv[0])
        try:
            with open(os.path.join(SLASH_PROC, str(pid_maydaemon), PROG_CMDLN)) as stream:
                other_cmdline = stream.read().split('\0')
            if other_cmdline and other_cmdline[-1] == "":
                other_cmdline.pop()
        except IOError as e:
            if e.errno == errno.ENOENT:
                # no process with the PID extracted from the
                # pidfile, so no problem to remove the latter
                os.unlink(pidfile)
                return
            raise
        # Check the whole command line of the other process
        if i_am in list(map(c14n_prog_name, other_cmdline)):
            LOG.warning(
                "A pidfile %r already exists (contains pid %d) and the "
                "correponding process command line contains our own name %r",
                pidfile,
                pid_maydaemon,
                i_am,
            )
            return
        # It may not be us, but we must be quite sure about that so also try
        # to validate with the name of the executable.
        full_pgm = lock_pgm = None
        try:
            full_pgm = os.readlink(
                os.path.join(SLASH_PROC, str(pid_maydaemon), PROG_SLINK)
            )
            lock_pgm = os.path.basename(full_pgm)
        except OSError as e:
            if e.errno == errno.EACCES:
                # We consider it's ok not being able to access
                # "/proc/<pid>/exe" if we could previously access
                # "/proc/<pid>/cmdline", because if we do not have
                # the needed permissions to run the daemon this will
                # be catched latter (potentially when creating our
                # own pidfile)
                lock_pgm = None
            else:
                raise
        if i_am == lock_pgm:
            LOG.warning(
                "A pidfile %r already exists (contains pid %d) and an "
                "executable with our name %r is runnning with that pid.",
                pidfile,
                pid_maydaemon,
                i_am,
            )
            return
        # Ok to remove the previously existing pidfile now.
        LOG.info(
            "A pidfile %r already exists (contains pid %d) but the "
            "corresponding process does not seem to match with our own name %r.  "
            "Will remove the pidfile.",
            pidfile,
            pid_maydaemon,
            i_am,
        )
        LOG.info("Splitted command line of the other process: %s", other_cmdline)
        if lock_pgm:
            LOG.info(
                "Name of the executable the other process comes from: %s", full_pgm
            )
        os.unlink(pidfile)
        return
    except Exception:  # pylint: disable-msg=W0703
        LOG.exception("unexpected error")


def take_file_lock(own_file, lock_file, own_content):
    """
    Atomically "move" @own_file to @lock_file if the latter does not exists,
    else just remove @own_file.

    @own_file: filepath of the temporary file that contains our PID
    @lock_file: destination filepath
    @own_content: content of @own_file

    Return True if the lock has been successfully taken, else False.
    (Caller should also be prepared for OSError exceptions)
    """
    try:
        try:
            os.link(own_file, lock_file)
        finally:
            os.unlink(own_file)
    except OSError as e:
        if e.errno == errno.EEXIST:
            LOG.warning(
                "The lock file %r already exists - won't "
                "overwrite it.  An other instance of ourself "
                "is probably running.",
                lock_file,
            )
            return False
        raise
    with open(lock_file) as stream:
        content = stream.read(len(own_content) + 1)
    if content != own_content:
        LOG.warning(
            "I thought I successfully took the lock file %r but "
            "it does not contain what was expected.  Somebody is "
            "playing with us.",
            lock_file,
        )
        return False
    return True


class PidfileLockError(RuntimeError):
    """The PID file could not be claimed without replacing another owner."""


def lock_pidfile(pidfile):
    """Claim a PID file and return this process's PID, without exiting.

    Existing stale-file detection and atomic hard-link acquisition are retained.
    Contention raises PidfileLockError; filesystem failures propagate unchanged.
    The caller owns the lock until unlock_pidfile() is called. Temporary files
    are removed even when writing or setting permissions fails.
    """
    pid = os.getpid()
    remove_if_stale_pidfile(pidfile)
    pid_write_file = pidfile + '.' + str(pid)
    temporary_created = False
    try:
        with open(pid_write_file, 'w') as fpid:
            temporary_created = True
            fpid.write("%s\n" % pid)
        os.chmod(pid_write_file, 0o644)
        if not take_file_lock(pid_write_file, pidfile, "%s\n" % pid):
            raise PidfileLockError("unable to claim pidfile: %r" % pidfile)
    finally:
        # take_file_lock normally unlinks this file itself. Do not hide the
        # original acquisition failure if best-effort cleanup also fails.
        try:
            if temporary_created:
                os.unlink(pid_write_file)
        except OSError as error:
            if error.errno != errno.ENOENT:
                LOG.warning("unable to remove temporary pidfile %r: %s",
                            pid_write_file, error)
    return pid


def lock_pidfile_or_die(pidfile):
    """Launcher compatibility: return the PID or exit with status 1.

    Embedded callers should use lock_pidfile() to handle errors themselves.
    """
    try:
        return lock_pidfile(pidfile)
    except PidfileLockError:
        sys.exit(1)
    except Exception:
        LOG.exception("unable to take pidfile")
        sys.exit(1)


@contextmanager
def locked_pidfile(pidfile):
    """Hold a PID file for a block, without daemonization or process exit."""
    pid = lock_pidfile(pidfile)
    try:
        yield pid
    finally:
        unlock_pidfile(pidfile)


def unlock_pidfile(pidfile):
    """
    @pidfile:
        path to the pidfile that will be removed if it is not too unsafe
    """
    try:
        pid = "%s\n" % os.getpid()
        with open(pidfile) as stream:
            content = stream.read(len(pid) + 1)
        if content == pid:
            os.unlink(pidfile)
        else:
            LOG.error("can not force unlock the pidfile of others")
    except (IOError, OSError) as e:
        LOG.error("%s: %s", type(e).__name__, e)


def daemonize():
    """
    Daemonize the program, ie. make it run in the "background", detach
    it from its controlling terminal and from its controlling process
    group session.

    NOTES:
        - This function also umask(0) and chdir("/")
        - stdin, stdout, and stderr are redirected from/to /dev/null

    SEE ALSO:
        http://www.unixguide.net/unix/programming/1.7.shtml
    """
    try:
        pid = os.fork()
        if pid > 0:
            os.waitpid(pid, 0)
            os._exit(0)  # pylint: disable-msg=W0212
    except OSError as e:
        LOG.exception("first fork() failed: %d (%s)", e.errno, e.strerror)
        sys.exit(1)

    os.setsid()
    os.umask(0)
    os.chdir("/")

    try:
        pid = os.fork()
        if pid > 0:
            os._exit(0)  # pylint: disable-msg=W0212
    except OSError as e:
        LOG.exception("second fork() failed: %d (%s)", e.errno, e.strerror)
        sys.exit(1)

    devnull_fd = None
    try:
        devnull_fd = os.open(os.devnull, os.O_RDWR)

        for stdf in (sys.__stdout__, sys.__stderr__):
            try:
                stdf.flush()
            except Exception:  # pylint: disable-msg=W0703
                pass

        for stdf in (sys.__stdin__, sys.__stdout__, sys.__stderr__):
            try:
                os.dup2(devnull_fd, stdf.fileno())
            except OSError:
                pass
    except Exception:  # pylint: disable-msg=W0703
        LOG.exception("error during file descriptor redirection")
    finally:
        if devnull_fd is not None and devnull_fd > 2:
            os.close(devnull_fd)


@contextmanager
def pidfile_context(pid_file_name, foreground=False):
    if not foreground:
        LOG.debug("Daemonizing...")
        daemonize()
        LOG.debug("Daemonized.")

    LOG.debug("Locking PID file...")
    lock_pidfile_or_die(pid_file_name)
    LOG.debug("PID file locked.")
    try:
        yield
    finally:
        LOG.debug("Unlocking PID...")
        unlock_pidfile(pid_file_name)
        LOG.debug("PID file unlocked.")

