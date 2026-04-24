import serial
import serial.tools.list_ports
import threading
import logging
import time
from typing import Optional, Any, Callable
from core.service import GatewayService
from protocol.codec import ProtocolCodec

logger = logging.getLogger("SerialServer")

class SerialServer(threading.Thread):
    """Bridge for UART serial communication, integrated with GatewayService."""

    def __init__(self, service: GatewayService, port: str = "COM3", baudrate: int = 115200, timeout: int = 1, retry_delay: Optional[int] = None):
        super().__init__()
        self.service = service
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.retry_delay = retry_delay
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False

    def run(self) -> None:
        """Background thread for serial IO."""
        self.running = True
        while self.running:
            try:
                if not self.serial_conn or not self.serial_conn.is_open:
                    logger.info(f"Connecting to Serial {self.port} ({self.baudrate})...")
                    self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
                    logger.info(f"Connected to {self.port}.")

                raw_line_bytes = self.serial_conn.readline()
                if raw_line_bytes:
                    try:
                        raw_line = raw_line_bytes.decode('utf-8').strip()
                        if raw_line:
                            logger.info(f"Serial In: {raw_line}")
                            event = ProtocolCodec.decode(raw_line)
                            if event:
                                self.service.handle_event(event)
                            else:
                                logger.warning(f"Unrecognized serial message: {raw_line}")
                    except UnicodeDecodeError:
                        logger.warning("Malformed serial data.")
            
            except (serial.SerialException, Exception) as e:
                if self.running:
                    logger.error(f"Serial Error: {e}")
                    if self.retry_delay is not None:
                        logger.info(f"Retrying in {self.retry_delay}s...")
                        self._cleanup()
                        time.sleep(self.retry_delay)
                    else:
                        logger.error("No retry strategy. Stopping SerialServer.")
                        self.running = False
                else:
                    logger.debug("Serial connection broken during shutdown (expected).")

    def send_command(self, command_str: str) -> None:
        """Sends a command to the serial device."""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                msg = f"{command_str}\n"
                self.serial_conn.write(msg.encode('utf-8'))
                logger.info(f"Serial Out: {command_str}")
            except Exception as e:
                logger.error(f"Failed to write to serial: {e}")
        else:
            logger.error("Serial connection unavailable for outgoing command.")

    def stop(self) -> None:
        self.running = False
        self._cleanup()

    def _cleanup(self) -> None:
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            self.serial_conn = None
            logger.info("Serial connection closed.")
