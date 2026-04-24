import json
import logging
from typing import List, Optional
from core.models import SensorReading, ConfigCommand
from .events import (
    AppEvent, RegisterUserEvent, AddControllerEvent,
    RemoveControllerEvent, ListControllersEvent,
    DataRequestEvent, ConfigCommandEvent, SensorReadingEvent
)

logger = logging.getLogger("ProtocolCodec")

# Cles de capteurs reconnues dans un payload JSON ou "pipe" venant du micro:bit.
_SENSOR_KEYS = {"T", "H", "L", "P"}
# Retro-compat (usage legacy du nom).
_JSON_SENSOR_KEYS = _SENSOR_KEYS


def _looks_like_hex(raw: str) -> bool:
    """True si la chaine est entierement hexadecimale et de longueur paire.

    Sert a detecter un payload chiffre XOR+hex sur la liaison serie.
    """
    if not raw or len(raw) % 2 != 0:
        return False
    for ch in raw:
        if ch not in "0123456789abcdefABCDEF":
            return False
    return True


def _xor_bytes(data: bytes, secret: bytes) -> bytes:
    if not secret:
        return data
    return bytes(b ^ secret[i % len(secret)] for i, b in enumerate(data))

class ProtocolCodec:
    """Handles parsing of raw strings into domain events and vice versa.

    Protocole UDP (app <-> serveur) :
        INIT,<passkey>                           enregistre / "login" l'utilisateur
        ADD,<passkey>,<controller_id>[,ts]       revendique un micro:bit
        REMOVE,<passkey>,<controller_id>[,ts]    libere un micro:bit + purge data
        LIST,<passkey>                           liste les controllers de l'utilisateur
        GET,<passkey>[,<controller_id>][,ts]     dernieres donnees (filtrable)
        <controller_id>,CONFIG,<order>           ordre d'affichage OLED

    Protocole UART (passerelle -> serveur) :
        <controller_id>,<sensor_id>,<value>      lecture capteur
    """

    @staticmethod
    def decode(raw_data: str) -> Optional[AppEvent]:
        if not raw_data or ',' not in raw_data:
            return None

        parts = [p.strip() for p in raw_data.split(',')]

        try:
            match parts:
                case ["INIT", passkey]:
                    return RegisterUserEvent(passkey=passkey)

                case ["ADD", passkey, controller_id, timestamp]:
                    return AddControllerEvent(
                        passkey=passkey,
                        controller_id=controller_id,
                        timestamp=int(timestamp),
                    )

                case ["ADD", passkey, controller_id]:
                    return AddControllerEvent(passkey=passkey, controller_id=controller_id)

                case ["REMOVE", passkey, controller_id, timestamp]:
                    return RemoveControllerEvent(
                        passkey=passkey,
                        controller_id=controller_id,
                        timestamp=int(timestamp),
                    )

                case ["REMOVE", passkey, controller_id]:
                    return RemoveControllerEvent(
                        passkey=passkey, controller_id=controller_id
                    )

                case ["LIST", passkey]:
                    return ListControllersEvent(passkey=passkey)

                case ["GET", passkey, controller_id, timestamp]:
                    return DataRequestEvent(
                        passkey=passkey,
                        controller_id=controller_id,
                        timestamp=int(timestamp),
                    )

                case ["GET", passkey, controller_id]:
                    # 3 args -> toujours un controller_id (meme s'il ressemble a un nombre).
                    # Pour un GET global sans controller, utiliser "GET,<passkey>".
                    return DataRequestEvent(passkey=passkey, controller_id=controller_id)

                case ["GET", passkey]:
                    return DataRequestEvent(passkey=passkey)

                case [controller_id, "CONFIG", value]:
                    return ConfigCommandEvent(
                        config=ConfigCommand(controller_id=controller_id, display_order=value)
                    )

                case [controller_id, sensor_id, value]:
                    return SensorReadingEvent(
                        reading=SensorReading(
                            controller_id=controller_id,
                            sensor_id=sensor_id,
                            value=float(value),
                        )
                    )

                case _:
                    logger.warning(f"Unrecognized protocol pattern: {parts}")
                    return None

        except (ValueError, TypeError) as e:
            logger.debug(f"Error decoding protocol message '{raw_data}': {e}")
            return None

    @staticmethod
    def decode_json_sensor_batch(raw: str, default_controller_id: str) -> List[SensorReadingEvent]:
        """Parse un payload JSON multi-capteurs emis par le micro:bit objet.

        Format attendu (cles optionnelles) :
            {"T":25.3, "H":42, "L":300, "P":1013}
            {"id":"17", "T":25.3, "H":42}

        L'attribution se fait via la cle "id" si presente, sinon via
        ``default_controller_id`` passe par la couche serie.
        """
        raw = raw.strip()
        if not raw.startswith("{"):
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.debug(f"Invalid JSON payload from micro:bit: {raw!r} ({exc})")
            return []
        if not isinstance(data, dict):
            return []

        controller_id = str(data.get("id", default_controller_id)).strip()
        if not controller_id:
            return []

        events: List[SensorReadingEvent] = []
        for key, value in data.items():
            if key not in _JSON_SENSOR_KEYS:
                continue
            try:
                f_value = float(value)
            except (TypeError, ValueError):
                logger.debug(f"Skipping non-numeric JSON value for {key}: {value!r}")
                continue
            events.append(SensorReadingEvent(
                reading=SensorReading(
                    controller_id=controller_id,
                    sensor_id=key,
                    value=f_value,
                )
            ))
        return events

    @staticmethod
    def decrypt_xor_hex(hex_str: str, secret: bytes) -> Optional[str]:
        """Decode hex -> XOR avec le secret partage -> string UTF-8.

        Retourne None si le hex est invalide ou si le plaintext n'est pas UTF-8.
        """
        hex_str = hex_str.strip()
        if not _looks_like_hex(hex_str):
            return None
        try:
            cipher = bytes.fromhex(hex_str)
        except ValueError:
            return None
        plain = _xor_bytes(cipher, secret)
        try:
            return plain.decode("utf-8")
        except UnicodeDecodeError:
            return None

    @staticmethod
    def encrypt_xor_hex(plain: str, secret: bytes) -> str:
        """Symetrique de decrypt_xor_hex : utilise pour les tests et l'outillage."""
        return _xor_bytes(plain.encode("utf-8"), secret).hex().upper()

    @staticmethod
    def decode_pipe_payload(raw: str) -> List[SensorReadingEvent]:
        """Parse le format envoye par le micro:bit objet :
            <device_id>|T:25.3,H:42,P:999
        Retourne une liste vide si le format ne correspond pas.
        """
        raw = raw.strip()
        if "|" not in raw:
            return []
        device_id, _, body = raw.partition("|")
        device_id = device_id.strip()
        if not device_id:
            return []

        events: List[SensorReadingEvent] = []
        for chunk in body.split(","):
            if ":" not in chunk:
                continue
            key, _, value = chunk.partition(":")
            key = key.strip().upper()
            if key not in _SENSOR_KEYS:
                continue
            try:
                f_value = float(value.strip())
            except ValueError:
                continue
            events.append(SensorReadingEvent(
                reading=SensorReading(
                    controller_id=device_id,
                    sensor_id=key,
                    value=f_value,
                )
            ))
        return events

    @staticmethod
    def parse_pairing(raw: str) -> Optional[tuple]:
        """Parse "PAIR|<secret>|<device_id>". Retourne (secret, device_id) ou None."""
        raw = raw.strip()
        if not raw.startswith("PAIR|"):
            return None
        parts = raw.split("|", 2)
        if len(parts) != 3:
            return None
        return (parts[1], parts[2].strip())

    @staticmethod
    def encode_config(config: ConfigCommand) -> str:
        return f"{config.controller_id},CONFIG,{config.display_order}"

    @staticmethod
    def encode_reading(reading: SensorReading) -> str:
        return f"{reading.controller_id},{reading.sensor_id},{reading.value}"
