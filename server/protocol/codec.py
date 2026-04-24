import json
import logging
import os
from typing import List, Optional

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from cryptography.hazmat.backends import default_backend

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

AES_BLOCK_SIZE_BYTES = 16
AES_KEY_SIZE_BYTES = 16   # AES-128


def _looks_like_hex(raw: str) -> bool:
    """True si la chaine est entierement hexadecimale et de longueur paire."""
    if not raw or len(raw) % 2 != 0:
        return False
    for ch in raw:
        if ch not in "0123456789abcdefABCDEF":
            return False
    return True


def derive_aes_key(secret: str) -> bytes:
    """Materialise la cle AES-128 (16 octets) a partir du --shared-secret.

    Strategie : zero-padding ou troncature sur 16 octets. Simple a reproduire
    cote micro:bit (compile-time constant dans micro/source/main.cpp).
    """
    b = secret.encode("utf-8")
    if len(b) >= AES_KEY_SIZE_BYTES:
        return b[:AES_KEY_SIZE_BYTES]
    return b + b"\x00" * (AES_KEY_SIZE_BYTES - len(b))

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
    def decrypt_aes_cbc_hex(hex_str: str, key: bytes) -> Optional[str]:
        """Dechiffre un payload hex(IV || ciphertext) encode par le micro:bit.

        - 16 premiers octets = IV
        - Le reste = ciphertext AES-128-CBC, padde PKCS7
        - La cle doit faire exactement 16 octets.

        Retourne None si la trame n'est pas valide (hex malforme, longueur,
        padding ou encodage UTF-8).
        """
        hex_str = hex_str.strip()
        if not _looks_like_hex(hex_str):
            return None
        try:
            data = bytes.fromhex(hex_str)
        except ValueError:
            return None

        # Il faut au moins un IV (16 o.) + un bloc chiffre (16 o.).
        if len(data) < 2 * AES_BLOCK_SIZE_BYTES:
            return None
        if (len(data) - AES_BLOCK_SIZE_BYTES) % AES_BLOCK_SIZE_BYTES != 0:
            return None
        if len(key) != AES_KEY_SIZE_BYTES:
            logger.error(f"AES key has {len(key)} bytes, expected {AES_KEY_SIZE_BYTES}")
            return None

        iv = data[:AES_BLOCK_SIZE_BYTES]
        ciphertext = data[AES_BLOCK_SIZE_BYTES:]

        try:
            decryptor = Cipher(
                algorithms.AES(key), modes.CBC(iv), backend=default_backend()
            ).decryptor()
            padded = decryptor.update(ciphertext) + decryptor.finalize()
            unpadder = PKCS7(AES_BLOCK_SIZE_BYTES * 8).unpadder()
            plain = unpadder.update(padded) + unpadder.finalize()
        except ValueError:
            return None

        try:
            return plain.decode("utf-8")
        except UnicodeDecodeError:
            return None

    @staticmethod
    def encrypt_aes_cbc_hex(plain: str, key: bytes, iv: Optional[bytes] = None) -> str:
        """Chiffre plain en AES-128-CBC, retourne hex(IV || ciphertext).

        ``iv`` est optionnel : si None, un IV cryptographiquement sur est
        genere via os.urandom. Utile a surcharger pour les tests.
        """
        if len(key) != AES_KEY_SIZE_BYTES:
            raise ValueError(f"AES key must be {AES_KEY_SIZE_BYTES} bytes")
        if iv is None:
            iv = os.urandom(AES_BLOCK_SIZE_BYTES)
        elif len(iv) != AES_BLOCK_SIZE_BYTES:
            raise ValueError(f"IV must be {AES_BLOCK_SIZE_BYTES} bytes")

        padder = PKCS7(AES_BLOCK_SIZE_BYTES * 8).padder()
        padded = padder.update(plain.encode("utf-8")) + padder.finalize()
        encryptor = Cipher(
            algorithms.AES(key), modes.CBC(iv), backend=default_backend()
        ).encryptor()
        ciphertext = encryptor.update(padded) + encryptor.finalize()
        return (iv + ciphertext).hex().upper()

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
