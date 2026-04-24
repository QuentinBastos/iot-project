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

# Cles de capteurs reconnues dans un payload JSON venant du micro:bit.
_JSON_SENSOR_KEYS = {"T", "H", "L", "P"}

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
    def encode_config(config: ConfigCommand) -> str:
        return f"{config.controller_id},CONFIG,{config.display_order}"

    @staticmethod
    def encode_reading(reading: SensorReading) -> str:
        return f"{reading.controller_id},{reading.sensor_id},{reading.value}"
