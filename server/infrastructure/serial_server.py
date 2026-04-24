import serial
import serial.tools.list_ports
import threading
import logging
import time
from typing import Optional, Any, Callable
from core.service import ServerService
from protocol.codec import ProtocolCodec

logger = logging.getLogger("SerialServer")

class SerialServer(threading.Thread):
    """Bridge for UART serial communication, integrated with ServerService."""

    def __init__(self, service: ServerService, port: str = "COM3", baudrate: int = 115200,
                 timeout: int = 1, retry_delay: Optional[int] = None,
                 default_controller_id: str = "default",
                 shared_secret: str = "groupe67"):
        super().__init__()
        self.service = service
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.retry_delay = retry_delay
        self.default_controller_id = default_controller_id
        self.shared_secret = shared_secret.encode("utf-8")
        self.shared_secret_text = shared_secret
        # device_ids qui ont reussi le handshake de pairing
        self.paired_devices: set[str] = set()
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
                            logger.debug(f"Serial In from {self.port}: '{raw_line}'")
                            self._dispatch_serial_line(raw_line)
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

    def _dispatch_serial_line(self, raw_line: str) -> None:
        """Route une ligne serie, en gerant trois couches :

            1. XOR+hex (micro:bit objet) -> dechiffre puis re-dispatch
            2. PAIR|<secret>|<id>        -> handshake, aucune data
            3. <id>|T:..,H:..            -> readings multi-capteurs
            4. {"T":..,"H":..}           -> readings JSON (compat v1)
            5. <ctrl>,<sensor>,<value>   -> trame CSV "classique"
        """
        # 1. Dechiffrement si payload hex (envoye par le micro:bit objet).
        if self._looks_hex(raw_line):
            plain = ProtocolCodec.decrypt_xor_hex(raw_line, self.shared_secret)
            if plain is None:
                logger.warning(f"Failed to decrypt hex payload: {raw_line}")
                return
            logger.debug(f"Decrypted payload: {plain!r}")
            raw_line = plain

        # 2. Pairing handshake.
        pair = ProtocolCodec.parse_pairing(raw_line)
        if pair is not None:
            secret, device_id = pair
            if secret == self.shared_secret_text and device_id:
                self.paired_devices.add(device_id)
                logger.info(f"Pairing OK: device '{device_id}' now trusted")
            else:
                logger.warning(f"Pairing rejected for device '{device_id}' (bad secret)")
            return

        # 3. Format pipe "<id>|T:..,H:..".
        if "|" in raw_line and ":" in raw_line:
            events = ProtocolCodec.decode_pipe_payload(raw_line)
            if events:
                for ev in events:
                    self.service.handle_event(ev)
                return

        # 4. JSON multi-capteurs.
        if raw_line.startswith("{"):
            events = ProtocolCodec.decode_json_sensor_batch(
                raw_line, self.default_controller_id
            )
            if events:
                for ev in events:
                    self.service.handle_event(ev)
                return
            logger.warning(f"Unrecognized JSON payload: {raw_line}")
            return

        # 5. Trame classique (CSV).
        event = ProtocolCodec.decode(raw_line)
        if event:
            self.service.handle_event(event)
            return

        logger.warning(f"Unrecognized serial message: {raw_line}")

    @staticmethod
    def _looks_hex(s: str) -> bool:
        # Meme heuristique que le codec mais sans import croise pour garder
        # cette couche autonome vis-a-vis des details internes du codec.
        if not s or len(s) % 2 != 0:
            return False
        return all(c in "0123456789abcdefABCDEF" for c in s)

    def send_command(self, command_str: str) -> None:
        """Sends a command to the serial device."""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                msg = f"{command_str}\n"
                self.serial_conn.write(msg.encode('utf-8'))
                logger.debug(f"Serial Out to {self.port}: '{command_str}'")
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

