import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from protocol.codec import ProtocolCodec
from protocol.events import (
    RegisterUserEvent, AddControllerEvent, RemoveControllerEvent,
    ListControllersEvent, DataRequestEvent, HistoryRequestEvent,
    ConfigCommandEvent, SensorReadingEvent, SensorSnapshotEvent,
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

    def test_decode_get_data_numeric_controller(self):
        # Un controller_id numerique (ex: "17") ne doit pas etre confondu avec un timestamp.
        event = ProtocolCodec.decode("GET,pass123,17")
        self.assertIsInstance(event, DataRequestEvent)
        self.assertEqual(event.controller_id, "17")
        self.assertIsNone(event.timestamp)

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

    # ---- decode_json_sensor_batch ----

    def test_decode_history_request(self):
        event = ProtocolCodec.decode("HISTORY,pass123,MC01,14")
        self.assertIsInstance(event, HistoryRequestEvent)
        self.assertEqual(event.controller_id, "MC01")
        self.assertEqual(event.days, 14)

        event2 = ProtocolCodec.decode("HISTORY,pass123,MC01")
        self.assertIsInstance(event2, HistoryRequestEvent)
        self.assertEqual(event2.days, 7)  # defaut

    def test_json_batch_produces_single_snapshot(self):
        events = ProtocolCodec.decode_json_sensor_batch(
            '{"T":25.3, "H":42, "P":999}', default_controller_id="17"
        )
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], SensorSnapshotEvent)
        snap = events[0].snapshot
        self.assertEqual(snap.controller_id, "17")
        self.assertEqual(snap.temperature, 25.3)
        self.assertEqual(snap.humidity, 42.0)
        self.assertIsNone(snap.luminosity)
        self.assertEqual(snap.pressure, 999.0)

    def test_json_batch_id_override(self):
        events = ProtocolCodec.decode_json_sensor_batch(
            '{"id":"42", "T":20.0}', default_controller_id="default"
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].snapshot.controller_id, "42")

    def test_json_batch_ignores_unknown_keys(self):
        events = ProtocolCodec.decode_json_sensor_batch(
            '{"T":25, "UNKNOWN":99, "H":42}', default_controller_id="17"
        )
        self.assertEqual(len(events), 1)
        snap = events[0].snapshot
        self.assertEqual(snap.temperature, 25.0)
        self.assertEqual(snap.humidity, 42.0)

    def test_json_batch_invalid_json(self):
        self.assertEqual(
            ProtocolCodec.decode_json_sensor_batch("{not json", default_controller_id="17"),
            [],
        )

    def test_json_batch_non_numeric_value_skipped(self):
        events = ProtocolCodec.decode_json_sensor_batch(
            '{"T":"abc", "H":42}', default_controller_id="17"
        )
        self.assertEqual(len(events), 1)
        snap = events[0].snapshot
        self.assertIsNone(snap.temperature)
        self.assertEqual(snap.humidity, 42.0)

    # ---- AES-128-CBC + hex encryption ----

    def test_derive_aes_key_padding(self):
        from protocol.codec import derive_aes_key
        self.assertEqual(derive_aes_key("groupe67"), b"groupe67" + b"\x00" * 8)

    def test_derive_aes_key_truncation(self):
        from protocol.codec import derive_aes_key
        self.assertEqual(len(derive_aes_key("x" * 32)), 16)

    def test_aes_cbc_round_trip(self):
        from protocol.codec import derive_aes_key
        key = derive_aes_key("groupe67")
        plain = "5E90D3CB|T:25.3,H:42,P:999"
        cipher = ProtocolCodec.encrypt_aes_cbc_hex(plain, key)
        # Hex ASCII majuscule, IV (16o=32 hex) + >=1 bloc (32 hex) => >=64 chars.
        self.assertRegex(cipher, r"^[0-9A-F]+$")
        self.assertGreaterEqual(len(cipher), 64)
        self.assertEqual(ProtocolCodec.decrypt_aes_cbc_hex(cipher, key), plain)

    def test_aes_cbc_iv_fixed_vector(self):
        """Vecteur reproductible : avec un IV connu, la sortie est deterministe.
        Permet de verifier la compatibilite avec l'implementation micro:bit."""
        from protocol.codec import derive_aes_key
        key = derive_aes_key("groupe67")
        iv = bytes.fromhex("00112233445566778899AABBCCDDEEFF")
        plain = "ABC|T:1.0"
        cipher = ProtocolCodec.encrypt_aes_cbc_hex(plain, key, iv=iv)
        self.assertTrue(cipher.startswith(iv.hex().upper()))
        self.assertEqual(ProtocolCodec.decrypt_aes_cbc_hex(cipher, key), plain)

    def test_aes_cbc_invalid_hex(self):
        from protocol.codec import derive_aes_key
        key = derive_aes_key("groupe67")
        self.assertIsNone(ProtocolCodec.decrypt_aes_cbc_hex("ZZZZ", key))
        self.assertIsNone(ProtocolCodec.decrypt_aes_cbc_hex("ABC", key))

    def test_aes_cbc_wrong_key(self):
        from protocol.codec import derive_aes_key
        good = derive_aes_key("groupe67")
        bad = derive_aes_key("other")
        cipher = ProtocolCodec.encrypt_aes_cbc_hex("hello", good)
        # Mauvaise cle -> soit padding invalide, soit UTF-8 invalide -> None.
        self.assertIsNone(ProtocolCodec.decrypt_aes_cbc_hex(cipher, bad))

    # ---- Pipe payload <id>|T:..,H:..,P:.. ----

    def test_pipe_payload_basic(self):
        events = ProtocolCodec.decode_pipe_payload("ABC|T:25.3,H:42,P:999")
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], SensorSnapshotEvent)
        snap = events[0].snapshot
        self.assertEqual(snap.controller_id, "ABC")
        self.assertEqual(snap.temperature, 25.3)
        self.assertEqual(snap.humidity, 42.0)
        self.assertIsNone(snap.luminosity)
        self.assertEqual(snap.pressure, 999.0)

    def test_pipe_payload_ignores_unknown(self):
        events = ProtocolCodec.decode_pipe_payload("X|T:1.0,FOO:2,L:300")
        self.assertEqual(len(events), 1)
        snap = events[0].snapshot
        self.assertEqual(snap.temperature, 1.0)
        self.assertEqual(snap.luminosity, 300.0)
        self.assertIsNone(snap.humidity)

    def test_pipe_payload_no_pipe(self):
        self.assertEqual(ProtocolCodec.decode_pipe_payload("T:25.3,H:42"), [])

    # ---- Pairing ----

    def test_parse_pairing_ok(self):
        result = ProtocolCodec.parse_pairing("PAIR|groupe67|ABC")
        self.assertEqual(result, ("groupe67", "ABC"))

    def test_parse_pairing_rejects_other_format(self):
        self.assertIsNone(ProtocolCodec.parse_pairing("HELLO"))
        self.assertIsNone(ProtocolCodec.parse_pairing("PAIR|onlyone"))


if __name__ == '__main__':
    unittest.main()
