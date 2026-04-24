import logging
from typing import Optional, List, Tuple
from core.models import SensorReading, ConfigCommand
from .events import (
    AppEvent, RegisterUserEvent, AddSensorEvent, 
    RemoveSensorEvent, DataRequestEvent, ConfigCommandEvent, SensorReadingEvent
)

logger = logging.getLogger("ProtocolCodec")

class ProtocolCodec:
    """Handles parsing of raw strings into domain events and vice versa."""

    @staticmethod
    def decode(raw_data: str) -> Optional[AppEvent]:
        """Parses a comma-separated string into an AppEvent."""
        if not raw_data or ',' not in raw_data:
            return None

        parts = [p.strip() for p in raw_data.split(',')]
        
        try:
            match parts:
                case ["INIT", passkey]:
                    return RegisterUserEvent(passkey=passkey)

                case ["ADD", passkey, sensor_id, timestamp]:
                    return AddSensorEvent(passkey=passkey, sensor_id=sensor_id, timestamp=int(timestamp))

                case ["ADD", passkey, sensor_id]:
                    return AddSensorEvent(passkey=passkey, sensor_id=sensor_id)

                case ["REMOVE", passkey, sensor_id, timestamp]:
                    return RemoveSensorEvent(passkey=passkey, sensor_id=sensor_id, timestamp=int(timestamp))

                case ["REMOVE", passkey, sensor_id]:
                    return RemoveSensorEvent(passkey=passkey, sensor_id=sensor_id)

                case ["GET", passkey, timestamp]:
                    return DataRequestEvent(passkey=passkey, timestamp=int(timestamp))

                case ["GET", passkey]:
                    return DataRequestEvent(passkey=passkey)

                case [controller_id, "CONFIG", value]:
                    return ConfigCommandEvent(
                        config=ConfigCommand(controller_id=controller_id, display_order=value)
                    )

                case [controller_id, sensor_id, value]:
                    # Likely a sensor reading
                    return SensorReadingEvent(
                        reading=SensorReading(
                            controller_id=controller_id, 
                            sensor_id=sensor_id, 
                            value=float(value)
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
        """Encodes a ConfigCommand model into a protocol string."""
        return f"{config.controller_id},CONFIG,{config.display_order}"

    @staticmethod
    def encode_reading(reading: SensorReading) -> str:
        """Encodes a SensorReading model into a protocol string."""
        # Note: Usually outgoing from micro:bit, but useful for testing/simulation
        return f"{reading.controller_id},{reading.sensor_id},{reading.value}"
