import unittest
import sys
import os
import socket
import time
import tempfile
from unittest.mock import MagicMock, patch

# Add server to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from data.database import Database
from data.repository import IoTRepository
from core.service import GatewayService
from infrastructure.udp_server import UDPServer
from infrastructure.serial_server import SerialServer

class TestSystemFlowE2E(unittest.TestCase):
    def setUp(self):
        # Start serial patch manually to ensure it persists for background threads
        self.serial_patcher = patch('serial.Serial')
        self.mock_serial_class = self.serial_patcher.start()
        
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.db = Database(self.db_path)
        self.repo = IoTRepository(self.db)
        self.service = GatewayService(self.repo)
        
        # Setup Serial Mock
        self.mock_serial = MagicMock()
        self.mock_serial_class.return_value = self.mock_serial
        self.mock_serial.is_open = True
        # Set default to empty bytes to prevent decoding errors in background thread
        self.mock_serial.readline.return_value = b"" 
        
        # Initialize Servers
        self.udp_port = 0 # Use any available port
        self.udp_server = UDPServer(service=self.service, port=self.udp_port, host="127.0.0.1")
        self.serial_server = SerialServer(service=self.service, port="MOCK_COM", baudrate=115200)
        
        # Connect Service to Serial for outgoing commands
        self.service.set_command_sender(self.serial_server.send_command)
        
        # Start everything
        self.service.start()
        self.udp_server.start()
        self.serial_server.start()
        
        # Wait for dynamic port to be assigned
        timeout = 5
        start = time.time()
        while self.udp_server.server is None and time.time() - start < timeout:
            time.sleep(0.1)
            
        if self.udp_server.server:
            self.udp_port = self.udp_server.server.server_address[1]
        else:
            self.fail("UDP Server failed to start and assign port.")
            
        time.sleep(0.5) # Final buffer

    def tearDown(self):
        self.udp_server.stop()
        self.serial_server.stop()
        self.service.stop()
        
        self.udp_server.join(timeout=1)
        self.serial_server.join(timeout=1)
        
        # Stop serial patch
        self.serial_patcher.stop()
        
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_full_data_lifecycle(self):
        passkey = "user_secret"
        sensor_id = "TEMP_01"
        
        # 1. Register User & Add Sensor via UDP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2)
            
            # Register
            sock.sendto(f"INIT,{passkey}".encode(), ("127.0.0.1", self.udp_port))
            data, _ = sock.recvfrom(1024)
            self.assertEqual(data.decode(), "OK")
            
            # Add Sensor
            sock.sendto(f"ADD,{passkey},{sensor_id}".encode(), ("127.0.0.1", self.udp_port))
            data, _ = sock.recvfrom(1024)
            self.assertEqual(data.decode(), "OK")
            
            # 2. Simulate Serial Input (Micro:bit sending data)
            # We use a helper to return data once, then empty bytes to avoid flooding & StopIteration
            def serial_read_side_effect(*args, **kwargs):
                if not hasattr(serial_read_side_effect, 'called'):
                    serial_read_side_effect.called = True
                    return f"MC01,{sensor_id},24.8\n".encode()
                return b""
            
            self.mock_serial.readline.side_effect = serial_read_side_effect
            time.sleep(0.5) # Give the serial thread time to process the side_effect
            
            # 3. Request Data via UDP
            sock.sendto(f"GET,{passkey}".encode(), ("127.0.0.1", self.udp_port))
            data, _ = sock.recvfrom(1024)
            response = data.decode()
            self.assertIn(f"MC01,{sensor_id},24.8", response)
            
            # 4. Trigger Config Command via UDP -> Expect Serial Output
            sock.sendto(f"MC01,CONFIG,TLH".encode(), ("127.0.0.1", self.udp_port))
            time.sleep(1.0)
            
            # Verify Serial Output
            self.mock_serial.write.assert_called_with(b"MC01,CONFIG,TLH\n")

if __name__ == '__main__':
    unittest.main()
