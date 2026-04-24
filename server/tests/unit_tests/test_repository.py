import unittest
import sys
import os
import datetime
import tempfile
from typing import List

# Add server to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from data.database import Database
from data.repository import IoTRepository, hash_passkey
from core.models import SensorReading, ConfigCommand

class TestIoTRepository(unittest.TestCase):
    def setUp(self):
        # Use a temporary file for the database to ensure schema persistence across connections
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.db = Database(self.db_path)
        self.repo = IoTRepository(self.db)
        self.passkey = "test_pass"
        self.passkey_hash = hash_passkey(self.passkey)

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_user_registration(self):
        self.assertFalse(self.repo.is_user_valid(self.passkey_hash))
        self.repo.register_user(self.passkey_hash)
        self.assertTrue(self.repo.is_user_valid(self.passkey_hash))

    def test_sensor_assignment_and_retrieval(self):
        self.repo.register_user(self.passkey_hash)
        
        # Add sensors
        self.assertTrue(self.repo.add_user_sensor(self.passkey_hash, "TEMP01"))
        self.assertTrue(self.repo.add_user_sensor(self.passkey_hash, "HUMID01"))
        
        sensors = self.repo.get_user_sensors(self.passkey_hash)
        self.assertIn("TEMP01", sensors)
        self.assertIn("HUMID01", sensors)
        self.assertEqual(len(sensors), 2)

    def test_prevent_duplicate_sensor_assignment(self):
        other_hash = hash_passkey("other_pass")
        self.repo.register_user(self.passkey_hash)
        self.repo.register_user(other_hash)
        
        self.repo.add_user_sensor(self.passkey_hash, "SHARED_SENSOR")
        # Attempt to add to another user should fail (return False)
        result = self.repo.add_user_sensor(other_hash, "SHARED_SENSOR")
        self.assertFalse(result)

    def test_reading_insertion_and_user_fetch(self):
        self.repo.register_user(self.passkey_hash)
        self.repo.add_user_sensor(self.passkey_hash, "TEMP01")
        
        reading = SensorReading(
            controller_id="MC01",
            sensor_id="TEMP01",
            value=25.5,
            timestamp=datetime.datetime.now()
        )
        self.repo.insert_reading(reading)
        
        # Fetch latest readings for user
        results = self.repo.get_latest_readings_for_user(self.passkey_hash)
        self.assertEqual(len(results), 1)
        # Result format: (controller_id, sensor_id, value, timestamp)
        self.assertEqual(results[0][0], "MC01")
        self.assertEqual(results[0][1], "TEMP01")
        self.assertEqual(results[0][2], 25.5)

    def test_configuration_persistence(self):
        config = ConfigCommand(controller_id="MC01", display_order="TLH")
        self.repo.set_configuration(config)
        
        saved_config = self.repo.get_configuration("MC01")
        self.assertEqual(saved_config, "TLH")
        
        # Test update
        self.repo.set_configuration(ConfigCommand(controller_id="MC01", display_order="HTL"))
        self.assertEqual(self.repo.get_configuration("MC01"), "HTL")

    def test_remove_sensor(self):
        self.repo.register_user(self.passkey_hash)
        self.repo.add_user_sensor(self.passkey_hash, "TEMP01")
        self.repo.remove_user_sensor(self.passkey_hash, "TEMP01")
        
        sensors = self.repo.get_user_sensors(self.passkey_hash)
        self.assertNotIn("TEMP01", sensors)

if __name__ == '__main__':
    unittest.main()
