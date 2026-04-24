import socketserver
import threading
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Tuple, Optional
from core.service import ServerService
from protocol.codec import ProtocolCodec

logger = logging.getLogger("UDPServer")

@dataclass
class RateLimitRecord:
    count: int = 0
    window_expiry: float = 0.0

_rate_limits: Dict[str, RateLimitRecord] = defaultdict(RateLimitRecord)

def is_rate_limited(ip: str) -> bool:
    now = time.time()
    record = _rate_limits[ip]
    if now > record.window_expiry:
        record.count = 1
        record.window_expiry = now + 10
        return False
    record.count += 1
    return record.count > 50

class UDPServerHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        try:
            raw_data: str = self.request[0].strip().decode('utf-8')
            socket = self.request[1]
            client_address: Tuple[str, int] = self.client_address
            
            if is_rate_limited(client_address[0]):
                logger.warning(f"Rate limit exceeded for {client_address[0]}")
                return

            logger.debug(f"UDP In from {client_address[0]}:{client_address[1]}: '{raw_data}'")

            event = ProtocolCodec.decode(raw_data)
            if event:
                response = self.server.service.handle_event(event)
                if response:
                    logger.debug(f"UDP Out to {client_address[0]}:{client_address[1]}: '{response}'")
                    socket.sendto(response.encode('utf-8'), client_address)
            else:
                logger.debug(f"Received unparsable UDP message: {raw_data}")

        except Exception as e:
            logger.error(f"Error in UDP handler: {e}")

class ThreadedUDPServer(socketserver.ThreadingMixIn, socketserver.UDPServer):
    def __init__(self, server_address: Tuple[str, int], RequestHandlerClass: Any, service: ServerService):
        super().__init__(server_address, RequestHandlerClass)
        self.service = service

class UDPServer(threading.Thread):
    def __init__(self, service: ServerService, port: int = 10000, host: str = "0.0.0.0"):
        super().__init__()
        self.service = service
        self.host = host
        self.port = port
        self.server: Optional[ThreadedUDPServer] = None

    def run(self) -> None:
        try:
            self.server = ThreadedUDPServer((self.host, self.port), UDPServerHandler, self.service)
            logger.info(f"UDP Server listening on {self.host}:{self.port}")
            self.server.serve_forever()
        except Exception as e:
            logger.error(f"UDP Server failed: {e}")

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logger.info("UDP Server shut down.")

