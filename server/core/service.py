import logging
import math
import time
from typing import Optional, Callable
from core.models import SensorReading, ConfigCommand
from data.repository import IoTRepository, hash_passkey
from protocol.events import (
    AppEvent, RegisterUserEvent, AddControllerEvent,
    RemoveControllerEvent, ListControllersEvent,
    DataRequestEvent, ConfigCommandEvent, SensorReadingEvent
)

logger = logging.getLogger("ServerService")

class ServerService:
    """Core business logic service for the IoT Server."""

    def __init__(self, repository: IoTRepository):
        self.repository = repository
        self.running = False
        self._command_sender: Optional[Callable[[str], None]] = None

    def set_command_sender(self, sender_callback: Callable[[str], None]) -> None:
        """Sets the callback for outgoing commands (e.g., to serial)."""
        self._command_sender = sender_callback

    def start(self) -> None:
        self.running = True
        logger.info("Server Service started.")

    def stop(self) -> None:
        self.running = False
        logger.info("Server Service stopped.")

    def handle_event(self, event: AppEvent) -> Optional[str]:
        match event:
            case RegisterUserEvent(passkey):
                return self._handle_register_user(passkey)
            case AddControllerEvent(passkey, controller_id, timestamp):
                return self._handle_add_controller(passkey, controller_id, timestamp)
            case RemoveControllerEvent(passkey, controller_id, timestamp):
                return self._handle_remove_controller(passkey, controller_id, timestamp)
            case ListControllersEvent(passkey):
                return self._handle_list_controllers(passkey)
            case DataRequestEvent(passkey, controller_id, timestamp):
                return self._handle_data_request(passkey, controller_id, timestamp)
            case ConfigCommandEvent(config):
                return self._handle_config_command(config)
            case SensorReadingEvent(reading):
                return self._handle_sensor_reading(reading)
            case _:
                logger.warning(f"Unhandled event type: {type(event).__name__}")
                return None

    # ------------------------------------------------------------------

    def _handle_sensor_reading(self, reading: SensorReading) -> None:
        try:
            if math.isnan(reading.value) or math.isinf(reading.value) or abs(reading.value) > 1_000_000:
                logger.warning(f"Sensor value out of bounds: {reading.value}")
                return

            self.repository.insert_reading(reading)
            logger.info(f"Data Stored: {reading.controller_id}/{reading.sensor_id}: {reading.value}")
        except (ValueError, TypeError):
            logger.warning(f"Invalid sensor value: {reading.value}")

    def _handle_config_command(self, config: ConfigCommand) -> None:
        clean_order = config.display_order.strip()
        if not clean_order:
            logger.warning("Invalid config: empty display order.")
            return

        self.repository.set_configuration(config)
        logger.info(f"Config saved for {config.controller_id}: {clean_order}")

        if self._command_sender:
            command_str = f"{config.controller_id},CONFIG,{clean_order}"
            self._command_sender(command_str)
        else:
            logger.warning("No command sender; config not broadcast.")

    def _handle_register_user(self, passkey: str) -> str:
        if not passkey:
            return "ERROR: Missing passkey"

        self.repository.register_user(hash_passkey(passkey))
        logger.info("New user registered (or already existed).")
        return "OK"

    def _handle_add_controller(self, passkey: str, controller_id: str,
                               timestamp: Optional[int]) -> str:
        if timestamp is not None and not self._is_timestamp_valid(timestamp):
            return "ERROR: Invalid or expired timestamp"
        if not controller_id:
            return "ERROR: Missing controller_id"

        h = hash_passkey(passkey)
        if not self.repository.is_user_valid(h):
            return "UNAUTHORIZED"

        if not self.repository.add_user_controller(h, controller_id):
            return "ERROR: Controller already claimed"

        logger.info(f"Controller {controller_id} added for user.")
        return "OK"

    def _handle_remove_controller(self, passkey: str, controller_id: str,
                                  timestamp: Optional[int]) -> str:
        if timestamp is not None and not self._is_timestamp_valid(timestamp):
            return "ERROR: Invalid or expired timestamp"
        if not controller_id:
            return "ERROR: Missing controller_id"

        h = hash_passkey(passkey)
        if not self.repository.is_user_valid(h):
            return "UNAUTHORIZED"

        if not self.repository.remove_user_controller(h, controller_id):
            return "ERROR: Controller not owned"

        logger.info(f"Controller {controller_id} removed (data purged).")
        return "OK"

    def _handle_list_controllers(self, passkey: str) -> str:
        h = hash_passkey(passkey)
        if not self.repository.is_user_valid(h):
            return "UNAUTHORIZED"

        ids = self.repository.get_user_controllers(h)
        return "\n".join(ids) if ids else ""

    def _handle_data_request(self, passkey: str, controller_id: Optional[str],
                             timestamp: Optional[int]) -> str:
        if timestamp is not None and not self._is_timestamp_valid(timestamp):
            return "ERROR: Invalid or expired timestamp"

        h = hash_passkey(passkey)
        if not self.repository.is_user_valid(h):
            return "UNAUTHORIZED"

        if controller_id:
            readings = self.repository.get_latest_readings_for_controller(h, controller_id)
            if readings is None:
                return "UNAUTHORIZED"
        else:
            readings = self.repository.get_latest_readings_for_user(h)

        if not readings:
            return "No data available"

        return "\n".join(f"{r[0]},{r[1]},{r[2]}" for r in readings)

    def _is_timestamp_valid(self, ts: int) -> bool:
        return abs(time.time() - ts) <= 10
