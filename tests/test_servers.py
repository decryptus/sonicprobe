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
