import sys
import signal
import time
import logging
import argparse
from typing import Optional, Any

from data.database import Database
from data.repository import IoTRepository
from core.service import ServerService
from infrastructure.udp_server import UDPServer
from infrastructure.serial_server import SerialServer

# Base logging configuration (level will be updated in main)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("storage/server.log")
    ]
)
logger = logging.getLogger("IoTApp")

class IoTApplication:
    """The main application that wires all components together."""

    def __init__(self, db_path: str = "storage/server_data.db",
                 serial_port: str = "COM3", baudrate: int = 115200,
                 udp_port: int = 10000,
                 serial_retry: Optional[int] = None,
                 default_controller_id: str = "default"):

        # 1. Setup Persistence Layer
        self.db = Database(db_path)
        self.repository = IoTRepository(self.db)

        # 2. Setup Service Layer (Business Logic)
        self.service = ServerService(self.repository)

        # 3. Setup Infrastructure Layer (Networking)
        self.serial_server = SerialServer(
            service=self.service,
            port=serial_port,
            baudrate=baudrate,
            retry_delay=serial_retry,
            default_controller_id=default_controller_id,
        )
        self.udp_server = UDPServer(service=self.service, port=udp_port)

        # 4. Connect Service to Serial for outgoing commands
        self.service.set_command_sender(self.serial_server.send_command)

    def start(self) -> None:
        logger.info("Starting IoT Server...")
        self.service.start()
        self.serial_server.start()
        self.udp_server.start()
        logger.info("IoT Server is active. Use Ctrl+C to stop.")

        try:
            while self.service.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self, *args: Any) -> None:
        logger.info("Shutdown signaling initiated...")
        self.udp_server.stop()
        self.serial_server.stop()
        self.service.stop()
        logger.info("Shutdown complete.")
        sys.exit(0)

def main() -> None:
    parser = argparse.ArgumentParser(description="IoT Server - Refactored Architecture")
    parser.add_argument("--serial_port", type=str, default="COM3", help="Serial port (e.g., COM3, /dev/ttyUSB0)")
    parser.add_argument("--baudrate", type=int, default=115200, help="Baudrate (default: 115200)")
    parser.add_argument("--udp_port", type=int, default=10000, help="UDP LISTEN port (default: 10000)")
    parser.add_argument("--db", type=str, default="storage/server_data.db", help="Path to SQLite database")
    parser.add_argument("--serial-retry", type=int, nargs='?', const=5, help="Retry delay (seconds) if serial port fails")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--default-controller",
        type=str,
        default="default",
        help=(
            "Controller ID utilise pour les payloads JSON recus du micro:bit "
            "quand la cle 'id' est absente (defaut: 'default')."
        ),
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Debug logging enabled.")

    app = IoTApplication(
        db_path=args.db,
        serial_port=args.serial_port,
        baudrate=args.baudrate,
        udp_port=args.udp_port,
        serial_retry=args.serial_retry,
        default_controller_id=args.default_controller,
    )

    signal.signal(signal.SIGINT, app.stop)
    signal.signal(signal.SIGTERM, app.stop)

    app.start()

if __name__ == "__main__":
    main()

