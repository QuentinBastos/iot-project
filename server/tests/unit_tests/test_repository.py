import unittest
import sys
import os
import datetime
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from data.database import Database
from data.repository import IoTRepository, hash_passkey
from core.models import SensorReading, ConfigCommand


class TestIoTRepository(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.db = Database(self.db_path)
        self.repo = IoTRepository(self.db)
        self.passkey = "test_pass"
        self.passkey_hash = hash_passkey(self.passkey)

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _add_reading(self, controller_id: str, sensor_id: str, value: float) -> None:
        self.repo.insert_reading(SensorReading(
            controller_id=controller_id,
            sensor_id=sensor_id,
            value=value,
            timestamp=datetime.datetime.now(),
        ))

    def test_user_registration(self):
        self.assertFalse(self.repo.is_user_valid(self.passkey_hash))
        self.repo.register_user(self.passkey_hash)
        self.assertTrue(self.repo.is_user_valid(self.passkey_hash))

    def test_controller_assignment_and_retrieval(self):
        self.repo.register_user(self.passkey_hash)
        self.assertTrue(self.repo.add_user_controller(self.passkey_hash, "MC01"))
        self.assertTrue(self.repo.add_user_controller(self.passkey_hash, "MC02"))

        ctrls = self.repo.get_user_controllers(self.passkey_hash)
        self.assertEqual(sorted(ctrls), ["MC01", "MC02"])

    def test_prevent_cross_user_controller_claim(self):
        other_hash = hash_passkey("other_pass")
        self.repo.register_user(self.passkey_hash)
        self.repo.register_user(other_hash)

        self.assertTrue(self.repo.add_user_controller(self.passkey_hash, "MC01"))
        self.assertFalse(self.repo.add_user_controller(other_hash, "MC01"))

    def test_idempotent_readd(self):
        self.repo.register_user(self.passkey_hash)
        self.assertTrue(self.repo.add_user_controller(self.passkey_hash, "MC01"))
        # Re-adding the same controller for the same user is a no-op success.
        self.assertTrue(self.repo.add_user_controller(self.passkey_hash, "MC01"))

    def test_user_owns_controller(self):
        self.repo.register_user(self.passkey_hash)
        self.repo.add_user_controller(self.passkey_hash, "MC01")
        self.assertTrue(self.repo.user_owns_controller(self.passkey_hash, "MC01"))
        self.assertFalse(self.repo.user_owns_controller(self.passkey_hash, "MC99"))

    def test_reading_insertion_and_user_fetch(self):
        self.repo.register_user(self.passkey_hash)
        self.repo.add_user_controller(self.passkey_hash, "MC01")
        self._add_reading("MC01", "TEMP", 25.5)
        self._add_reading("MC01", "HUM", 40.0)
        # A reading from an unowned controller should not be returned
        self._add_reading("MC99", "TEMP", 99.9)

        results = self.repo.get_latest_readings_for_user(self.passkey_hash)
        self.assertEqual(len(results), 2)
        sensors = {row[1]: row[2] for row in results}
        self.assertEqual(sensors["TEMP"], 25.5)
        self.assertEqual(sensors["HUM"], 40.0)

    def test_readings_per_controller(self):
        self.repo.register_user(self.passkey_hash)
        self.repo.add_user_controller(self.passkey_hash, "MC01")
        self.repo.add_user_controller(self.passkey_hash, "MC02")
        self._add_reading("MC01", "TEMP", 22.0)
        self._add_reading("MC02", "TEMP", 30.0)

        mc01 = self.repo.get_latest_readings_for_controller(self.passkey_hash, "MC01")
        self.assertIsNotNone(mc01)
        self.assertEqual(len(mc01), 1)
        self.assertEqual(mc01[0][0], "MC01")
        self.assertEqual(mc01[0][2], 22.0)

        # Unauthorized controller -> None
        self.assertIsNone(
            self.repo.get_latest_readings_for_controller(self.passkey_hash, "MC99")
        )

    def test_configuration_persistence(self):
        config = ConfigCommand(controller_id="MC01", display_order="TLH")
        self.repo.set_configuration(config)
        self.assertEqual(self.repo.get_configuration("MC01"), "TLH")

        self.repo.set_configuration(ConfigCommand(controller_id="MC01", display_order="HTL"))
        self.assertEqual(self.repo.get_configuration("MC01"), "HTL")

    def test_remove_controller_also_purges_data(self):
        self.repo.register_user(self.passkey_hash)
        self.repo.add_user_controller(self.passkey_hash, "MC01")
        self._add_reading("MC01", "TEMP", 25.0)
        self.repo.set_configuration(ConfigCommand(controller_id="MC01", display_order="TLH"))

        self.assertTrue(self.repo.remove_user_controller(self.passkey_hash, "MC01"))

        self.assertNotIn("MC01", self.repo.get_user_controllers(self.passkey_hash))
        # readings + configurations should be purged
        self.assertEqual(
            self.repo.get_latest_readings_for_user(self.passkey_hash), []
        )
        self.assertIsNone(self.repo.get_configuration("MC01"))

    def test_remove_controller_not_owned(self):
        self.repo.register_user(self.passkey_hash)
        self.assertFalse(self.repo.remove_user_controller(self.passkey_hash, "MC99"))


if __name__ == '__main__':
    unittest.main()
