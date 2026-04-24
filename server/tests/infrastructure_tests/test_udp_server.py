import unittest
import sys
import os
import socket
import time
from unittest.mock import MagicMock

# Add server to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from infrastructure.udp_server import UDPServer
from core.service import ServerService
from protocol.events import RegisterUserEvent

class TestUDPServerInfrastructure(unittest.TestCase):
    def setUp(self):
        self.mock_service = MagicMock(spec=ServerService)
        self.port = 10005 # Use a dedicated port for testing
        self.server = UDPServer(service=self.mock_service, port=self.port, host="127.0.0.1")
        self.server.start()
        time.sleep(0.5) # Wait for server to bind

    def tearDown(self):
        self.server.stop()
        self.server.join(timeout=2)

    def test_udp_request_response(self):
        # Configure mock response
        self.mock_service.handle_event.return_value = "OK_FROM_SERVICE"
        
        # Send UDP packet
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1)
            message = "INIT,test_pass"
            sock.sendto(message.encode('utf-8'), ("127.0.0.1", self.port))
            
            # Receive response
            data, addr = sock.recvfrom(1024)
            self.assertEqual(data.decode('utf-8'), "OK_FROM_SERVICE")
        
        # Verify service was called with correct event
        self.mock_service.handle_event.assert_called_once()
        args, _ = self.mock_service.handle_event.call_args
        event = args[0]
        self.assertIsInstance(event, RegisterUserEvent)
        self.assertEqual(event.passkey, "test_pass")

    def test_rate_limiting(self):
        # Configure mock response to avoid 'MagicMock' .encode() error
        self.mock_service.handle_event.return_value = "OK"
        
        # The rate limit is 50 requests per 10 seconds per IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            message = "INIT,rate_test"
            
            # Send 60 requests rapidly
            for i in range(60):
                sock.sendto(message.encode('utf-8'), ("127.0.0.1", self.port))
                # No need to receive responses here, just hitting the limit
            
        # The service should have been called at most 50 times
        self.assertLessEqual(self.mock_service.handle_event.call_count, 50)

if __name__ == '__main__':
    unittest.main()

