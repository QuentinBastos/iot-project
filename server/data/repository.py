import hashlib
import functools
import logging
import datetime
from typing import List, Tuple, Optional, Any
from .database import Database
from core.models import SensorReading, ConfigCommand

logger = logging.getLogger("IoTRepository")
STATIC_SALT = "iot_server_static_salt_v2"

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

    # ------------------------------------------------------------------
    # Readings
    # ------------------------------------------------------------------

    def insert_reading(self, reading: SensorReading) -> None:
        with self.db.connection() as conn:
            cursor = conn.cursor()
            now_str = reading.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')
            cursor.execute('''
                INSERT INTO readings (controller_id, sensor_id, value, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (reading.controller_id, reading.sensor_id, reading.value, now_str))

    def get_latest_readings_for_user(self, passkey_hash: str) -> List[Tuple[str, str, float, str]]:
        """Dernieres lectures de TOUS les controllers appartenant a l'utilisateur."""
        controllers = self.get_user_controllers(passkey_hash)
        if not controllers:
            return []
        return self._latest_for_controllers(controllers)

    def get_latest_readings_for_controller(
        self, passkey_hash: str, controller_id: str
    ) -> Optional[List[Tuple[str, str, float, str]]]:
        """Dernieres lectures d'un controller specifique.

        Retourne None si le controller n'appartient pas a l'utilisateur.
        Retourne [] si le controller appartient mais n'a pas encore de donnees.
        """
        if not self.user_owns_controller(passkey_hash, controller_id):
            return None
        return self._latest_for_controllers([controller_id])

    def _latest_for_controllers(
        self, controller_ids: List[str]
    ) -> List[Tuple[str, str, float, str]]:
        with self.db.connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join(['?'] * len(controller_ids))
            query = f'''
                SELECT controller_id, sensor_id, value, timestamp
                FROM readings
                WHERE id IN (
                    SELECT MAX(id)
                    FROM readings
                    WHERE controller_id IN ({placeholders})
                    GROUP BY controller_id, sensor_id
                )
                ORDER BY controller_id, sensor_id
            '''
            cursor.execute(query, controller_ids)
            return cursor.fetchall()

    # ------------------------------------------------------------------
    # Configurations
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # User <-> Controllers
    # ------------------------------------------------------------------

    def add_user_controller(self, passkey_hash: str, controller_id: str) -> bool:
        """Associe un controller a un utilisateur.

        Retourne False si le controller appartient deja a un autre utilisateur.
        Re-ajouter un controller deja possede par le meme utilisateur est un no-op success.
        """
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT passkey_hash FROM user_controllers WHERE controller_id = ?",
                (controller_id,),
            )
            existing = cursor.fetchone()
            if existing and existing[0] != passkey_hash:
                logger.info(
                    f"Prevented claim of already-assigned controller {controller_id}."
                )
                return False

            cursor.execute('''
                INSERT OR IGNORE INTO user_controllers (passkey_hash, controller_id)
                VALUES (?, ?)
            ''', (passkey_hash, controller_id))
            return True

    def remove_user_controller(self, passkey_hash: str, controller_id: str) -> bool:
        """Supprime l'association ET purge les donnees stockees du controller.

        Retourne True uniquement si l'utilisateur possedait bien ce controller.
        """
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM user_controllers WHERE passkey_hash = ? AND controller_id = ?",
                (passkey_hash, controller_id),
            )
            if cursor.fetchone() is None:
                return False

            cursor.execute(
                "DELETE FROM user_controllers WHERE passkey_hash = ? AND controller_id = ?",
                (passkey_hash, controller_id),
            )
            cursor.execute(
                "DELETE FROM readings WHERE controller_id = ?", (controller_id,)
            )
            cursor.execute(
                "DELETE FROM configurations WHERE controller_id = ?", (controller_id,)
            )
            return True

    def get_user_controllers(self, passkey_hash: str) -> List[str]:
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT controller_id FROM user_controllers
                WHERE passkey_hash = ?
                ORDER BY controller_id
            ''', (passkey_hash,))
            return [row[0] for row in cursor.fetchall()]

    def user_owns_controller(self, passkey_hash: str, controller_id: str) -> bool:
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM user_controllers WHERE passkey_hash = ? AND controller_id = ?",
                (passkey_hash, controller_id),
            )
            return cursor.fetchone() is not None
