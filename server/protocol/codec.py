import logging
from typing import Optional
from core.models import SensorReading, ConfigCommand
from .events import (
    AppEvent, RegisterUserEvent, AddControllerEvent,
    RemoveControllerEvent, ListControllersEvent,
    DataRequestEvent, ConfigCommandEvent, SensorReadingEvent
)

logger = logging.getLogger("ProtocolCodec")

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

                case ["GET", passkey, arg]:
                    # Distinguer "GET,passkey,<timestamp>" de "GET,passkey,<controller_id>"
                    if arg.isdigit():
                        return DataRequestEvent(passkey=passkey, timestamp=int(arg))
                    return DataRequestEvent(passkey=passkey, controller_id=arg)

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
    def encode_config(config: ConfigCommand) -> str:
        return f"{config.controller_id},CONFIG,{config.display_order}"

    @staticmethod
    def encode_reading(reading: SensorReading) -> str:
        return f"{reading.controller_id},{reading.sensor_id},{reading.value}"
