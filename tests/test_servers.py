import threading
import unittest
from six.moves import socketserver
from sonicprobe.libs.threading_tcp_server import KillableThreadingTCPServer, KillableDynThreadingTCPServer
from sonicprobe.libs.threading_udp_server import KillableThreadingUDPServer, KillableDynThreadingUDPServer

class ServerTests(unittest.TestCase):
    def test_idle_servers_stop_without_an_incoming_connection(self):
        for server_class in (KillableThreadingTCPServer, KillableDynThreadingTCPServer,
                             KillableThreadingUDPServer, KillableDynThreadingUDPServer):
            server = server_class({'max_workers': 1}, ('127.0.0.1', 0), socketserver.BaseRequestHandler)
            thread = threading.Thread(target=server.serve_until_killed)
            thread.daemon = True
            thread.start()
            try:
                server.kill()
                thread.join(2)
                self.assertFalse(thread.is_alive(), server_class.__name__)
            finally:
                server.kill(); server.server_close()

    def test_saturated_servers_stop_accepting_and_close_queued_requests(self):
        try:
            from unittest import mock
        except ImportError:
            import mock
        for server_class in (KillableThreadingTCPServer, KillableDynThreadingTCPServer,
                             KillableThreadingUDPServer, KillableDynThreadingUDPServer):
            entered, release = threading.Event(), threading.Event()
            class Handler(socketserver.BaseRequestHandler):
                def handle(self):
                    entered.set()
                    release.wait(4)
            server = server_class({'max_workers': 1}, ('127.0.0.1', 0), Handler)
            requests = [mock.Mock(), mock.Mock(), mock.Mock()]
            finished = threading.Event()
            def accept_last():
                server.handle_request()
                finished.set()
            thread = threading.Thread(target=accept_last)
            thread.daemon = True
            try:
                with mock.patch.object(server, 'get_request', side_effect=[
                        (request, ('127.0.0.1', 1234)) for request in requests]), \
                        mock.patch.object(server, 'shutdown_request') as close:
                    server.handle_request()
                    self.assertTrue(entered.wait(2))
                    server.handle_request()
                    thread.start()
                    server.kill()
                    self.assertTrue(finished.wait(2), server_class.__name__)
                    # Pending requests are closed even while the active handler
                    # remains blocked; kill() does not interrupt that handler.
                    closed = [call[0][0] for call in close.call_args_list]
                    self.assertIn(requests[1], closed)
                    self.assertIn(requests[2], closed)
                    release.set()
                    if hasattr(server, 'workerpool'):
                        server.workerpool.killall(2)
                    else:
                        server.requests.join()
                    closed = [call[0][0] for call in close.call_args_list]
                    self.assertEqual(len(closed), 3)
                    self.assertEqual(len(set(id(request) for request in closed)), 3)
            finally:
                release.set()
                server.kill()
                server.server_close()
                if thread.ident is not None:
                    thread.join(2)

    def test_fixed_and_dynamic_servers_handle_real_tcp_and_udp_requests(self):
        import socket
        for server_class in (KillableThreadingTCPServer, KillableDynThreadingTCPServer,
                             KillableThreadingUDPServer, KillableDynThreadingUDPServer):
            udp = issubclass(server_class, socketserver.UDPServer)
            class Echo(socketserver.BaseRequestHandler):
                def handle(self):
                    if udp:
                        data, sock = self.request
                        sock.sendto(data.upper(), self.client_address)
                    else:
                        self.request.sendall(self.request.recv(16).upper())
            server = server_class({'max_workers': 2, 'max_requests': 1},
                                  ('127.0.0.1', 0), Echo)
            thread = threading.Thread(target=server.serve_until_killed)
            thread.daemon = True
            thread.start()
            try:
                for _ in range(3):
                    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM)
                    client.settimeout(2)
                    try:
                        client.connect(server.server_address)
                        client.sendall(b'hello')
                        self.assertEqual(client.recv(16), b'HELLO')
                    finally:
                        client.close()
            finally:
                server.kill()
                thread.join(2)
                server.server_close()
            self.assertFalse(thread.is_alive())
