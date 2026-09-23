# -*- coding: utf-8 -*-
# Copyright (C) 2015-2019 Adrien Delle Cave
# SPDX-License-Identifier: GPL-3.0-or-later
"""sonicprobe.libs.threading_tcp_server"""

import logging
import threading
import time

from six.moves import queue, socketserver
from sonicprobe.libs.workerpool import WorkerPool

LOG = logging.getLogger('sonicprobe.threading-tcp-server')


class ThreadingHTTPServer(socketserver.ThreadingTCPServer):
    """
    Same as HTTPServer, but derives from ThreadingTCPServer instead of
    TCPServer so that each http handler instance runs in its own thread.
    """

    allow_reuse_address = 1    # Seems to make sense in testing environment

    def server_bind(self):
        """Override server_bind to store the server name."""
        socketserver.TCPServer.server_bind(self)
        host, port = self.socket.getsockname()[:2]
        self.server_name = socketserver.socket.getfqdn(host)
        self.server_port = port


class KillableDynThreadingTCPServer(socketserver.ThreadingTCPServer):
    _killed = False
    allow_reuse_address = 1    # Seems to make sense in testing environment

    def __init__(self, config, server_address, RequestHandlerClass, bind_and_activate = True, name = None):
        socketserver.ThreadingTCPServer.__init__(self, server_address, RequestHandlerClass, bind_and_activate)
        self.socket.settimeout(0.5)
        self._killed = False
        self._request_lock = threading.RLock()
        self._stop_event = threading.Event()

        max_workers     = int(config.get('max_workers', 0))
        max_requests    = int(config.get('max_requests', 0))
        max_life_time   = int(config.get('max_life_time', 0))

        if max_workers < 1:
            max_workers = 1

        self.requests   = queue.Queue()
        self._pending_requests = {}
        self.workerpool = WorkerPool(name        = name,
                                     max_workers = max_workers,
                                     max_tasks   = max_requests,
                                     life_time   = max_life_time)

    def kill(self):
        with self._request_lock:
            self._killed = True
            self._stop_event.set()
            pending = list(self._pending_requests.values())
            self._pending_requests.clear()
        self.workerpool.killall(0)
        for request in pending:
            self.shutdown_request(request)
        return self._killed

    def _process_queued_request(self, request, client_address):
        with self._request_lock:
            if id(request) not in self._pending_requests:
                return  # kill() already closed this pending request.
            del self._pending_requests[id(request)]
        self.process_request_thread(request, client_address)

    def killed(self):
        return self._killed

    def handle_request(self):
        """simply collect requests and put them on the queue for the workers."""
        try:
            request, client_address = self.get_request()
        except socketserver.socket.error:
            return

        if self.verify_request(request, client_address):
            with self._request_lock:
                if self._killed:
                    self.shutdown_request(request)
                    return
                self._pending_requests[id(request)] = request
                try:
                    self.workerpool.run(self._process_queued_request,
                                        request=request, client_address=client_address)
                except BaseException:
                    self._pending_requests.pop(id(request), None)
                    self.shutdown_request(request)
                    raise
        else:
            self.shutdown_request(request)

    def handle_error(self, request, client_address):
        LOG.debug("Exception happened during processing of request from: %r", client_address)
        LOG.debug("", exc_info = 1)

    def serve_until_killed(self):
        """Handle one request at a time until we are murdered."""
        while not self.killed():
            self.handle_request()


class KillableDynThreadingHTTPServer(KillableDynThreadingTCPServer, ThreadingHTTPServer):
    def server_bind(self):
        ThreadingHTTPServer.server_bind(self)


class KillableThreadingTCPServer(socketserver.ThreadingTCPServer):
    _killed = False
    allow_reuse_address = 1    # Seems to make sense in testing environment

    def __init__(self, config, server_address, RequestHandlerClass, bind_and_activate = True, name = None):
        socketserver.ThreadingTCPServer.__init__(self, server_address, RequestHandlerClass, bind_and_activate)
        self.socket.settimeout(0.5)
        self._killed = False
        self._request_lock = threading.RLock()
        self._stop_event = threading.Event()

        self.worker_name   = name

        self.max_workers   = int(config.get('max_workers', 0))
        self.max_requests  = int(config.get('max_requests', 0))
        self.max_life_time = int(config.get('max_life_time', 0))

        if self.max_workers < 1:
            self.max_workers = 1

        self.requests      = queue.Queue(self.max_workers)

        self.add_worker(self.max_workers)

    def kill(self):
        with self._request_lock:
            self._killed = True
            self._stop_event.set()
            while True:
                try:
                    request, _ = self.requests.get_nowait()
                except queue.Empty:
                    break
                try:
                    self.shutdown_request(request)
                finally:
                    self.requests.task_done()
        return self._killed

    def killed(self):
        return self._killed

    def add_worker(self, nb = 1, name = None):
        tname = name or self.worker_name or "Thread"

        for n in range(nb): # pylint: disable=unused-variable
            t = threading.Thread(target = self.process_request_thread,
                                 args   = (self,))
            t.name = "%s:%s" % (tname, t.name)
            t.daemon = True
            t.start()

    def process_request_thread(self, mainthread):  # pylint: disable=arguments-differ
        life_time = time.time()
        nb_requests = 0
        while not mainthread.killed():
            if self.max_life_time > 0 and time.time() - life_time >= self.max_life_time:
                if not mainthread.killed():
                    mainthread.add_worker(1)
                return
            try:
                request, client_address = self.requests.get(True, 0.5)
            except queue.Empty:
                continue
            try:
                with self._request_lock:
                    cancelled = mainthread.killed()
                if cancelled:
                    self.shutdown_request(request)
                    return
                socketserver.ThreadingTCPServer.process_request_thread(self, request, client_address)
            finally:
                self.requests.task_done()
            nb_requests += 1
            if self.max_requests > 0 and nb_requests >= self.max_requests:
                if not mainthread.killed():
                    mainthread.add_worker(1)
                return

    def handle_request(self):
        """simply collect requests and put them on the queue for the workers."""
        try:
            request, client_address = self.get_request()
        except socketserver.socket.error:
            return

        if self.verify_request(request, client_address):
            while True:
                with self._request_lock:
                    if self._killed:
                        self.shutdown_request(request)
                        return
                    try:
                        self.requests.put_nowait((request, client_address))
                        return
                    except queue.Full:
                        pass
                self._stop_event.wait(0.05)
        else:
            self.shutdown_request(request)

    def handle_error(self, request, client_address):
        LOG.debug("Exception happened during processing of request from: %r", client_address)
        LOG.debug("", exc_info = 1)

    def serve_until_killed(self):
        """Handle one request at a time until we are murdered."""
        while not self.killed():
            self.handle_request()


class KillableThreadingHTTPServer(KillableThreadingTCPServer, ThreadingHTTPServer):
    def server_bind(self):
        ThreadingHTTPServer.server_bind(self)


__all__ = [
    'ThreadingHTTPServer',
    'KillableThreadingTCPServer',
    'KillableThreadingHTTPServer',
    'KillableDynThreadingTCPServer',
    'KillableDynThreadingHTTPServer']
