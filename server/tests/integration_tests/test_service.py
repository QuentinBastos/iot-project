import unittest
import sys
import os
import time
import tempfile
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from data.database import Database
from data.repository import IoTRepository
from core.service import ServerService
from core.models import SensorReading, ConfigCommand
from protocol.events import (
    RegisterUserEvent, AddControllerEvent, RemoveControllerEvent,
    ListControllersEvent, DataRequestEvent, ConfigCommandEvent, SensorReadingEvent
)

class TestServerServiceIntegration(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.db = Database(self.db_path)
        self.repo = IoTRepository(self.db)
        self.service = ServerService(self.repo)
        self.service.start()

        self.passkey = "user123"
        self.controller_id = "MC01"

    def tearDown(self):
        self.service.stop()
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _register_and_claim(self, controller_id: str) -> None:
        self.service.handle_event(RegisterUserEvent(passkey=self.passkey))
        self.service.handle_event(AddControllerEvent(
            passkey=self.passkey, controller_id=controller_id
        ))

    def test_flow_registration_and_data_retrieval(self):
        resp = self.service.handle_event(RegisterUserEvent(passkey=self.passkey))
        self.assertEqual(resp, "OK")

        resp = self.service.handle_event(AddControllerEvent(
            passkey=self.passkey, controller_id=self.controller_id
        ))
        self.assertEqual(resp, "OK")

        reading = SensorReading(controller_id=self.controller_id, sensor_id="TEMP", value=22.5)
        self.service.handle_event(SensorReadingEvent(reading=reading))

        resp = self.service.handle_event(DataRequestEvent(passkey=self.passkey))
        self.assertIn("MC01,TEMP,22.5", resp)

    def test_data_request_filtered_by_controller(self):
        self._register_and_claim("MC01")
        self._register_and_claim("MC02")
        self.service.handle_event(SensorReadingEvent(
            reading=SensorReading(controller_id="MC01", sensor_id="TEMP", value=20.0)
        ))
        self.service.handle_event(SensorReadingEvent(
            reading=SensorReading(controller_id="MC02", sensor_id="TEMP", value=30.0)
        ))

        resp = self.service.handle_event(
            DataRequestEvent(passkey=self.passkey, controller_id="MC01")
        )
        self.assertIn("MC01,TEMP,20.0", resp)
        self.assertNotIn("MC02", resp)

    def test_data_request_unauthorized_controller(self):
        self.service.handle_event(RegisterUserEvent(passkey=self.passkey))
        resp = self.service.handle_event(
            DataRequestEvent(passkey=self.passkey, controller_id="MCXXX")
        )
        self.assertEqual(resp, "UNAUTHORIZED")

    def test_list_controllers(self):
        self._register_and_claim("MC01")
        self._register_and_claim("MC02")

        resp = self.service.handle_event(ListControllersEvent(passkey=self.passkey))
        self.assertEqual(sorted(resp.split("\n")), ["MC01", "MC02"])

    def test_list_controllers_unauthorized(self):
        resp = self.service.handle_event(ListControllersEvent(passkey="unknown"))
        self.assertEqual(resp, "UNAUTHORIZED")

    def test_remove_controller_purges_data(self):
        self._register_and_claim("MC01")
        self.service.handle_event(SensorReadingEvent(
            reading=SensorReading(controller_id="MC01", sensor_id="TEMP", value=21.0)
        ))

        resp = self.service.handle_event(RemoveControllerEvent(
            passkey=self.passkey, controller_id="MC01"
        ))
        self.assertEqual(resp, "OK")

        resp = self.service.handle_event(ListControllersEvent(passkey=self.passkey))
        self.assertEqual(resp, "")

        resp = self.service.handle_event(DataRequestEvent(passkey=self.passkey))
        self.assertEqual(resp, "No data available")

    def test_remove_controller_not_owned(self):
        self.service.handle_event(RegisterUserEvent(passkey=self.passkey))
        resp = self.service.handle_event(RemoveControllerEvent(
            passkey=self.passkey, controller_id="MCXXX"
        ))
        self.assertEqual(resp, "ERROR: Controller not owned")

    def test_security_access_denied(self):
        resp = self.service.handle_event(DataRequestEvent(passkey="attacker"))
        self.assertEqual(resp, "UNAUTHORIZED")

        resp = self.service.handle_event(AddControllerEvent(
            passkey="attacker", controller_id="MC01"
        ))
        self.assertEqual(resp, "UNAUTHORIZED")

    def test_config_command_broadcast(self):
        mock_sender = MagicMock()
        self.service.set_command_sender(mock_sender)

        config = ConfigCommand(controller_id="MC01", display_order="TLH")
        self.service.handle_event(ConfigCommandEvent(config=config))

        self.assertEqual(self.repo.get_configuration("MC01"), "TLH")
        mock_sender.assert_called_with("MC01,CONFIG,TLH")

    def test_timestamp_validation(self):
        self.service.handle_event(RegisterUserEvent(passkey=self.passkey))

        resp = self.service.handle_event(AddControllerEvent(
            passkey=self.passkey, controller_id="MC01", timestamp=int(time.time())
        ))
        self.assertEqual(resp, "OK")

        old_ts = int(time.time()) - 60
        resp = self.service.handle_event(AddControllerEvent(
            passkey=self.passkey, controller_id="MC02", timestamp=old_ts
        ))
        self.assertEqual(resp, "ERROR: Invalid or expired timestamp")


if __name__ == '__main__':
    unittest.main()

