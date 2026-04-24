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
from core.models import SensorReading, SensorSnapshot, ConfigCommand
from protocol.events import (
    RegisterUserEvent, AddControllerEvent, RemoveControllerEvent,
    ListControllersEvent, DataRequestEvent, HistoryRequestEvent,
    ConfigCommandEvent, SensorReadingEvent, SensorSnapshotEvent,
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

        # Le nouveau chemin principal : un snapshot multi-capteurs.
        self.service.handle_event(SensorSnapshotEvent(snapshot=SensorSnapshot(
            controller_id=self.controller_id, temperature=22.5, humidity=44.0
        )))

        # La reponse GET est explosee en 1 ligne par capteur (compat app).
        resp = self.service.handle_event(DataRequestEvent(passkey=self.passkey))
        self.assertIn(f"{self.controller_id},T,22.5", resp)
        self.assertIn(f"{self.controller_id},H,44.0", resp)

    def test_data_request_filtered_by_controller(self):
        self._register_and_claim("MC01")
        self._register_and_claim("MC02")
        self.service.handle_event(SensorSnapshotEvent(
            snapshot=SensorSnapshot(controller_id="MC01", temperature=20.0)
        ))
        self.service.handle_event(SensorSnapshotEvent(
            snapshot=SensorSnapshot(controller_id="MC02", temperature=30.0)
        ))

        resp = self.service.handle_event(
            DataRequestEvent(passkey=self.passkey, controller_id="MC01")
        )
        self.assertIn("MC01,T,20.0", resp)
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

    def test_history_request_returns_snapshots(self):
        self._register_and_claim("MC01")
        self.service.handle_event(SensorSnapshotEvent(
            snapshot=SensorSnapshot(controller_id="MC01", temperature=20.0, humidity=40.0)
        ))
        self.service.handle_event(SensorSnapshotEvent(
            snapshot=SensorSnapshot(controller_id="MC01", temperature=21.5, humidity=41.0,
                                    luminosity=300.0, pressure=1013.0)
        ))

        resp = self.service.handle_event(HistoryRequestEvent(
            passkey=self.passkey, controller_id="MC01", limit=10,
        ))
        lines = resp.split("\n")
        self.assertEqual(len(lines), 2)
        # Plus recent d'abord.
        self.assertIn("21.5", lines[0])
        self.assertIn("1013.0", lines[0])
        self.assertIn("20.0", lines[1])

    def test_history_request_unauthorized(self):
        self.service.handle_event(RegisterUserEvent(passkey=self.passkey))
        resp = self.service.handle_event(HistoryRequestEvent(
            passkey=self.passkey, controller_id="NOT_MINE",
        ))
        self.assertEqual(resp, "UNAUTHORIZED")

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

