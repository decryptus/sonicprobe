# -*- coding: utf8 -*-

import logging
import Queue
import SocketServer
import threading
import time

from SocketServer import socket

LOG = logging.getLogger('sonicprobe.threading-tcp-server')


class ThreadingHTTPServer(SocketServer.ThreadingTCPServer):
    """
    Same as HTTPServer, but derives from ThreadingTCPServer instead of
    TCPServer so that each http handler instance runs in its own thread.
    """

    allow_reuse_address = 1    # Seems to make sense in testing environment

    def server_bind(self):
        """Override server_bind to store the server name."""
        SocketServer.TCPServer.server_bind(self)
        host, port = self.socket.getsockname()[:2]
        self.server_name = socket.getfqdn(host)
        self.server_port = port


class KillableThreadingTCPServer(SocketServer.ThreadingTCPServer):
    """
    accepted_sockets = weakref.WeakSet()

    def nb_connections(self):
        return sum(1 for sock in self.accepted_sockets if sock.fileno() >= 0)

    def verify_request(self, request, client_address):
        if self.nb_connections() > 1:
            LOG.info("### NB connections: %r ###", self.nb_connections())

        self.accepted_sockets.add(self.socket)

        return ThreadingHTTPServer.verify_request(self, request, client_address)
    """

    "Just introduces serve_until_killed(), which is specific to this module"

    _killed = False
    allow_reuse_address = 1    # Seems to make sense in testing environment

    def __init__(self, config, server_address, RequestHandlerClass, bind_and_activate = True, name = None):
        SocketServer.TCPServer.__init__(self, server_address, RequestHandlerClass, bind_and_activate)

        self.worker_name   = name

        self.max_workers   = int(config.get('max_workers', 0))
        self.max_requests  = int(config.get('max_requests', 0))
        self.max_life_time = int(config.get('max_life_time', 0))

        if self.max_workers < 1:
            self.max_workers = 1

        self.requests      = Queue.Queue(self.max_workers)

        self.add_worker(self.max_workers)

    def kill(self):
        self._killed = True
        return self._killed

    def killed(self):
        return self._killed

    def add_worker(self, nb = 1, name = None):
        tname = name or self.worker_name or "Thread"

        for n in range(nb):
            t = threading.Thread(target = self.process_request_thread,
                                 args   = (self,))
            t.setName(threading._newname("%s:%%d" % tname))
            t.setDaemon(True)
            t.start()

    def process_request_thread(self, mainthread):
        """obtain request from queue instead of directly from server socket"""
        life_time   = time.time()
        nb_requests = 0

        while not mainthread.killed():
            if self.max_life_time > 0:
                if (time.time() - life_time) >= self.max_life_time:
                    mainthread.add_worker(1)
                    return
                try:
                    SocketServer.ThreadingTCPServer.process_request_thread(self, *self.requests.get(True, 0.5))
                except Queue.Empty:
                    continue
            else:
                SocketServer.ThreadingTCPServer.process_request_thread(self, *self.requests.get())

            LOG.debug("nb_requests: %d, max_requests: %d", nb_requests, self.max_requests)
            nb_requests += 1

            if self.max_requests > 0 and nb_requests >= self.max_requests:
                mainthread.add_worker(1)
                return

    def handle_request(self):
        """simply collect requests and put them on the queue for the workers."""
        try:
            request, client_address = self.get_request()
        except socket.error:
            return

        if self.verify_request(request, client_address):
            self.requests.put((request, client_address))

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


__all__ = ['ThreadingHTTPServer', 'KillableThreadingTCPServer', 'KillableThreadingHTTPServer']
