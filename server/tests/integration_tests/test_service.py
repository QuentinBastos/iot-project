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

    def test_history_request_returns_daily_aggregates(self):
        """HISTORY retourne min/max/moyenne par jour, pas les snapshots bruts."""
        import datetime as _dt
        self._register_and_claim("MC01")

        # Deux snapshots AUJOURD'HUI : le throttling memoire ne filtre pas
        # deux appels successifs si on force des timestamps espaces de >10s.
        # Le test atteint directement le repository pour controler l'aggregation
        # sans dependre du throttling du service.
        now = _dt.datetime.now()
        self.repo.insert_snapshot(SensorSnapshot(
            controller_id="MC01", temperature=20.0, humidity=40.0, timestamp=now
        ))
        self.repo.insert_snapshot(SensorSnapshot(
            controller_id="MC01", temperature=30.0, humidity=50.0, timestamp=now,
        ))

        resp = self.service.handle_event(HistoryRequestEvent(
            passkey=self.passkey, controller_id="MC01", days=7,
        ))
        # Une seule ligne (1 journee agregee) : day,Tavg,Tmin,Tmax,Havg,...,samples
        lines = resp.split("\n")
        self.assertEqual(len(lines), 1)
        parts = lines[0].split(",")
        # 1 day + 12 stats + 1 count = 14 colonnes
        self.assertEqual(len(parts), 14)
        self.assertEqual(parts[1], "25.00")  # T avg = (20+30)/2
        self.assertEqual(parts[2], "20.00")  # T min
        self.assertEqual(parts[3], "30.00")  # T max
        self.assertEqual(parts[-1], "2")      # samples

    def test_history_request_unauthorized(self):
        self.service.handle_event(RegisterUserEvent(passkey=self.passkey))
        resp = self.service.handle_event(HistoryRequestEvent(
            passkey=self.passkey, controller_id="NOT_MINE",
        ))
        self.assertEqual(resp, "UNAUTHORIZED")

    def test_snapshot_throttling_10s(self):
        """Deux snapshots espaces de moins de 10s -> un seul insert en base."""
        import datetime as _dt
        self._register_and_claim("MC01")

        t0 = _dt.datetime(2026, 4, 24, 12, 0, 0)
        self.service.handle_event(SensorSnapshotEvent(
            snapshot=SensorSnapshot(controller_id="MC01", temperature=20.0, timestamp=t0)
        ))
        # 5s plus tard -> ignoree
        self.service.handle_event(SensorSnapshotEvent(
            snapshot=SensorSnapshot(
                controller_id="MC01", temperature=21.0,
                timestamp=t0 + _dt.timedelta(seconds=5),
            )
        ))
        # 11s plus tard -> acceptee
        self.service.handle_event(SensorSnapshotEvent(
            snapshot=SensorSnapshot(
                controller_id="MC01", temperature=22.0,
                timestamp=t0 + _dt.timedelta(seconds=11),
            )
        ))
        history = self.repo.get_history_for_controller(
            __import__('data.repository', fromlist=['hash_passkey'])
            .hash_passkey(self.passkey),
            "MC01", limit=10,
        )
        self.assertEqual(len(history), 2)
        values = sorted(row[1] for row in history)
        self.assertEqual(values, [20.0, 22.0])

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

