import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from protocol.codec import ProtocolCodec
from protocol.events import (
    RegisterUserEvent, AddControllerEvent, RemoveControllerEvent,
    ListControllersEvent, DataRequestEvent, ConfigCommandEvent, SensorReadingEvent
)
from core.models import SensorReading, ConfigCommand

class TestProtocolCodec(unittest.TestCase):
    def test_decode_init(self):
        event = ProtocolCodec.decode("INIT,pass123")
        self.assertIsInstance(event, RegisterUserEvent)
        self.assertEqual(event.passkey, "pass123")

    def test_decode_add_controller(self):
        event = ProtocolCodec.decode("ADD,pass123,MC01")
        self.assertIsInstance(event, AddControllerEvent)
        self.assertEqual(event.passkey, "pass123")
        self.assertEqual(event.controller_id, "MC01")
        self.assertIsNone(event.timestamp)

        event = ProtocolCodec.decode("ADD,pass123,MC01,1617835200")
        self.assertIsInstance(event, AddControllerEvent)
        self.assertEqual(event.timestamp, 1617835200)

    def test_decode_remove_controller(self):
        event = ProtocolCodec.decode("REMOVE,pass123,MC01")
        self.assertIsInstance(event, RemoveControllerEvent)
        self.assertEqual(event.controller_id, "MC01")

    def test_decode_list_controllers(self):
        event = ProtocolCodec.decode("LIST,pass123")
        self.assertIsInstance(event, ListControllersEvent)
        self.assertEqual(event.passkey, "pass123")

    def test_decode_get_data_global(self):
        event = ProtocolCodec.decode("GET,pass123")
        self.assertIsInstance(event, DataRequestEvent)
        self.assertEqual(event.passkey, "pass123")
        self.assertIsNone(event.controller_id)
        self.assertIsNone(event.timestamp)

    def test_decode_get_data_filtered(self):
        event = ProtocolCodec.decode("GET,pass123,MC01")
        self.assertIsInstance(event, DataRequestEvent)
        self.assertEqual(event.controller_id, "MC01")
        self.assertIsNone(event.timestamp)

    def test_decode_get_data_with_timestamp_only(self):
        event = ProtocolCodec.decode("GET,pass123,1617835200")
        self.assertIsInstance(event, DataRequestEvent)
        self.assertEqual(event.timestamp, 1617835200)
        self.assertIsNone(event.controller_id)

    def test_decode_get_data_full(self):
        event = ProtocolCodec.decode("GET,pass123,MC01,1617835200")
        self.assertIsInstance(event, DataRequestEvent)
        self.assertEqual(event.controller_id, "MC01")
        self.assertEqual(event.timestamp, 1617835200)

    def test_decode_config(self):
        event = ProtocolCodec.decode("MC01,CONFIG,TLH")
        self.assertIsInstance(event, ConfigCommandEvent)
        self.assertEqual(event.config.controller_id, "MC01")
        self.assertEqual(event.config.display_order, "TLH")

    def test_decode_sensor_reading(self):
        event = ProtocolCodec.decode("MC01,TEMP,22.5")
        self.assertIsInstance(event, SensorReadingEvent)
        self.assertEqual(event.reading.controller_id, "MC01")
        self.assertEqual(event.reading.sensor_id, "TEMP")
        self.assertEqual(event.reading.value, 22.5)

    def test_decode_invalid(self):
        self.assertIsNone(ProtocolCodec.decode(""))
        self.assertIsNone(ProtocolCodec.decode("INVALID"))
        self.assertIsNone(ProtocolCodec.decode("MC01,TEMP,abc"))

    def test_encode_config(self):
        config = ConfigCommand(controller_id="MC02", display_order="HTL")
        self.assertEqual(ProtocolCodec.encode_config(config), "MC02,CONFIG,HTL")

    def test_encode_reading(self):
        reading = SensorReading(controller_id="MC01", sensor_id="HUM", value=45.0)
        self.assertEqual(ProtocolCodec.encode_reading(reading), "MC01,HUM,45.0")


if __name__ == '__main__':
    unittest.main()
