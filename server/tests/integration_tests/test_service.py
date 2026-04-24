import unittest
import sys
import os
import time
import tempfile
from unittest.mock import MagicMock

# Add server to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from data.database import Database
from data.repository import IoTRepository
from core.service import ServerService
from core.models import SensorReading, ConfigCommand
from protocol.events import (
    RegisterUserEvent, AddSensorEvent, DataRequestEvent, 
    ConfigCommandEvent, SensorReadingEvent
)

class TestServerServiceIntegration(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.db = Database(self.db_path)
        self.repo = IoTRepository(self.db)
        self.service = ServerService(self.repo)
        self.service.start()
        
        self.passkey = "user123"
        self.sensor_id = "TEMP01"

    def tearDown(self):
        self.service.stop()
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_flow_registration_and_data_retrieval(self):
        # 1. Register user
        resp = self.service.handle_event(RegisterUserEvent(passkey=self.passkey))
        self.assertEqual(resp, "OK")
        
        # 2. Add sensor
        resp = self.service.handle_event(AddSensorEvent(passkey=self.passkey, sensor_id=self.sensor_id))
        self.assertEqual(resp, "OK")
        
        # 3. Simulate sensor reading coming from Serial
        reading = SensorReading(controller_id="MC01", sensor_id=self.sensor_id, value=22.5)
        self.service.handle_event(SensorReadingEvent(reading=reading))
        
        # 4. Request data via UDP
        resp = self.service.handle_event(DataRequestEvent(passkey=self.passkey))
        self.assertIn("MC01,TEMP01,22.5", resp)

    def test_security_access_denied(self):
        # Request data for unregistered user
        resp = self.service.handle_event(DataRequestEvent(passkey="attacker"))
        self.assertEqual(resp, "UNAUTHORIZED")
        
        # Add sensor for unregistered user
        resp = self.service.handle_event(AddSensorEvent(passkey="attacker", sensor_id="S1"))
        self.assertEqual(resp, "UNAUTHORIZED")

    def test_config_command_broadcast(self):
        # Mock command sender
        mock_sender = MagicMock()
        self.service.set_command_sender(mock_sender)
        
        config = ConfigCommand(controller_id="MC01", display_order="TLH")
        self.service.handle_event(ConfigCommandEvent(config=config))
        
        # Verify it was saved
        saved = self.repo.get_configuration("MC01")
        self.assertEqual(saved, "TLH")
        
        # Verify it was broadcast to serial
        mock_sender.assert_called_with("MC01,CONFIG,TLH")

    def test_timestamp_validation(self):
        self.service.handle_event(RegisterUserEvent(passkey=self.passkey))
        
        # Valid timestamp (now)
        now_ts = int(time.time())
        resp = self.service.handle_event(AddSensorEvent(passkey=self.passkey, sensor_id="T1", timestamp=now_ts))
        self.assertEqual(resp, "OK")
        
        # Invalid timestamp (old)
        old_ts = int(time.time()) - 60 # 60 seconds old, limit is 10
        resp = self.service.handle_event(AddSensorEvent(passkey=self.passkey, sensor_id="T2", timestamp=old_ts))
        self.assertEqual(resp, "ERROR: Invalid or expired timestamp")

if __name__ == '__main__':
    unittest.main()

