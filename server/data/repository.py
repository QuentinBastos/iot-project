import hashlib
import functools
import logging
import datetime
from typing import List, Tuple, Optional, Any
from .database import Database
from core.models import SensorReading, ConfigCommand

logger = logging.getLogger("IoTRepository")
STATIC_SALT = "iot_gateway_static_salt_v2"

@functools.lru_cache(maxsize=128)
def hash_passkey(passkey: str) -> str:
    """Consistently hashes a passkey using PBKDF2."""
    passkey_bytes = passkey.encode('utf-8')
    salt_bytes = STATIC_SALT.encode('utf-8')
    key = hashlib.pbkdf2_hmac('sha256', passkey_bytes, salt_bytes, 200000)
    return key.hex()

class IoTRepository:
    """Handles data persistence logic using Repository Pattern."""

    def __init__(self, db: Database):
        self.db = db

    def insert_reading(self, reading: SensorReading) -> None:
        with self.db.connection() as conn:
            cursor = conn.cursor()
            now_str = reading.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')
            cursor.execute('''
                INSERT INTO readings (controller_id, sensor_id, value, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (reading.controller_id, reading.sensor_id, reading.value, now_str))

    def get_latest_readings_for_user(self, passkey_hash: str) -> List[Tuple[str, str, float, str]]:
        sensor_ids = self.get_user_sensors(passkey_hash)
        if not sensor_ids:
            return []

        with self.db.connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join(['?'] * len(sensor_ids))
            query = f'''
                SELECT controller_id, sensor_id, value, timestamp
                FROM readings
                WHERE id IN (
                    SELECT MAX(id)
                    FROM readings
                    WHERE sensor_id IN ({placeholders})
                    GROUP BY controller_id, sensor_id
                )
            '''
            cursor.execute(query, sensor_ids)
            return cursor.fetchall()

    def set_configuration(self, config: ConfigCommand) -> None:
        with self.db.connection() as conn:
            cursor = conn.cursor()
            now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
            cursor.execute('''
                INSERT INTO configurations (controller_id, display_order, timestamp)
                VALUES (?, ?, ?)
                ON CONFLICT(controller_id) DO UPDATE SET
                    display_order = excluded.display_order,
                    timestamp = excluded.timestamp
            ''', (config.controller_id, config.display_order, now_str))

    def get_configuration(self, controller_id: str) -> Optional[str]:
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT display_order FROM configurations WHERE controller_id = ?
            ''', (controller_id,))
            result = cursor.fetchone()
            return result[0] if result else None

    def register_user(self, passkey_hash: str) -> None:
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (passkey_hash)
                VALUES (?)
            ''', (passkey_hash,))

    def is_user_valid(self, passkey_hash: str) -> bool:
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM users WHERE passkey_hash = ?", (passkey_hash,))
            return cursor.fetchone() is not None

    def add_user_sensor(self, passkey_hash: str, sensor_id: str) -> bool:
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT passkey_hash FROM user_sensors WHERE sensor_id = ?", (sensor_id,))
            existing = cursor.fetchone()
            if existing and existing[0] != passkey_hash:
                logger.info(f"Prevented attempt to claim already-assigned sensor {sensor_id}.")
                return False

            cursor.execute('''
                INSERT OR IGNORE INTO user_sensors (passkey_hash, sensor_id)
                VALUES (?, ?)
            ''', (passkey_hash, sensor_id))
            return True

    def remove_user_sensor(self, passkey_hash: str, sensor_id: str) -> None:
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM user_sensors WHERE passkey_hash = ? AND sensor_id = ?
            ''', (passkey_hash, sensor_id))

    def get_user_sensors(self, passkey_hash: str) -> List[str]:
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT sensor_id FROM user_sensors WHERE passkey_hash = ?
            ''', (passkey_hash,))
            return [row[0] for row in cursor.fetchall()]
