import hashlib
import functools
import logging
import datetime
from typing import List, Tuple, Optional, Any
from .database import Database
from core.models import SensorReading, SensorSnapshot, ConfigCommand

logger = logging.getLogger("IoTRepository")
STATIC_SALT = "iot_server_static_salt_v2"


# Conversion snapshot -> lignes legacy (une ligne par capteur non-nul).
_SENSOR_COLUMN_TO_ID = (
    (1, "T"),  # temperature
    (2, "H"),  # humidity
    (3, "L"),  # luminosity
    (4, "P"),  # pressure
)


def _explode_snapshots(snapshots: List[Tuple]) -> List[Tuple[str, str, float, str]]:
    """Transforme (ctrl, T, H, L, P, ts) en plusieurs (ctrl, sensor_id, value, ts).

    Utilitaire pour garder la compat avec les anciens appelants qui attendaient
    une ligne par capteur.
    """
    out: List[Tuple[str, str, float, str]] = []
    for row in snapshots or []:
        ctrl, ts = row[0], row[5]
        for idx, sensor_id in _SENSOR_COLUMN_TO_ID:
            value = row[idx]
            if value is None:
                continue
            out.append((ctrl, sensor_id, float(value), ts))
    return out

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
    # Readings (snapshots multi-capteurs)
    # ------------------------------------------------------------------

    # Les readings sont stockes une ligne par snapshot. Les methodes ci-dessous
    # retournent les tuples :
    #   (controller_id, temperature, humidity, luminosity, pressure, timestamp)
    # Les champs capteurs peuvent etre None si la trame source ne les contenait
    # pas (typiquement le cas de la luminosite L sur le micro:bit actuel).
    READING_COLUMNS = (
        "controller_id, temperature, humidity, luminosity, pressure, timestamp"
    )

    def insert_snapshot(self, snapshot: SensorSnapshot) -> None:
        with self.db.connection() as conn:
            cursor = conn.cursor()
            now_str = snapshot.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')
            cursor.execute('''
                INSERT INTO readings
                    (controller_id, temperature, humidity, luminosity, pressure, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                snapshot.controller_id,
                snapshot.temperature,
                snapshot.humidity,
                snapshot.luminosity,
                snapshot.pressure,
                now_str,
            ))

    def insert_reading(self, reading: SensorReading) -> None:
        """Enveloppe legacy : une trame CSV "<ctrl>,<sensor>,<value>" devient un
        snapshot a un seul champ renseigne."""
        key = reading.sensor_id.strip().upper()
        mapping = {
            "T": "temperature", "TEMP": "temperature", "TEMPERATURE": "temperature",
            "H": "humidity", "HUM": "humidity", "HUMID": "humidity",
            "HUMIDITY": "humidity", "HUMIDITE": "humidity",
            "L": "luminosity", "LUM": "luminosity", "LUMIN": "luminosity",
            "LUMINOSITY": "luminosity", "LUMINOSITE": "luminosity",
            "P": "pressure", "PRES": "pressure", "PRESSURE": "pressure",
            "PRESSION": "pressure",
        }
        field = mapping.get(key)
        if field is None:
            logger.warning(f"Unknown legacy sensor_id '{reading.sensor_id}', ignored")
            return
        snapshot = SensorSnapshot(
            controller_id=reading.controller_id,
            timestamp=reading.timestamp,
            **{field: reading.value},
        )
        self.insert_snapshot(snapshot)

    def get_latest_snapshot_for_user(self, passkey_hash: str) -> List[Tuple]:
        """Dernier snapshot de CHAQUE controller appartenant a l'utilisateur."""
        controllers = self.get_user_controllers(passkey_hash)
        if not controllers:
            return []
        return self._latest_snapshots_for(controllers)

    def get_latest_snapshot_for_controller(
        self, passkey_hash: str, controller_id: str
    ) -> Optional[List[Tuple]]:
        """Dernier snapshot d'un controller specifique, liste d'un seul element
        pour la coherence avec get_latest_snapshot_for_user.

        Retourne None si le controller n'appartient pas a l'utilisateur.
        Retourne [] si le controller n'a pas encore de donnees.
        """
        if not self.user_owns_controller(passkey_hash, controller_id):
            return None
        return self._latest_snapshots_for([controller_id])

    def _latest_snapshots_for(self, controller_ids: List[str]) -> List[Tuple]:
        with self.db.connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join(["?"] * len(controller_ids))
            query = f'''
                SELECT {self.READING_COLUMNS}
                FROM readings
                WHERE id IN (
                    SELECT MAX(id) FROM readings
                    WHERE controller_id IN ({placeholders})
                    GROUP BY controller_id
                )
                ORDER BY controller_id
            '''
            cursor.execute(query, controller_ids)
            return cursor.fetchall()

    def get_history_for_controller(
        self, passkey_hash: str, controller_id: str, limit: int = 50
    ) -> Optional[List[Tuple]]:
        """Les ``limit`` derniers snapshots d'un controller, plus recent d'abord.

        Retourne None si le controller n'appartient pas a l'utilisateur.
        Conserve pour les outils / tests bas niveau (la route UDP HISTORY
        passe desormais par ``get_daily_aggregates_for_controller``).
        """
        if not self.user_owns_controller(passkey_hash, controller_id):
            return None
        limit = max(1, min(limit, 500))
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT {self.READING_COLUMNS} FROM readings "
                "WHERE controller_id = ? "
                "ORDER BY timestamp DESC, id DESC LIMIT ?",
                (controller_id, limit),
            )
            return cursor.fetchall()

    # Colonnes retournees par get_daily_aggregates_for_controller, dans l'ordre :
    AGGREGATE_COLUMNS = (
        "day,"
        "t_avg,t_min,t_max,"
        "h_avg,h_min,h_max,"
        "l_avg,l_min,l_max,"
        "p_avg,p_min,p_max,"
        "samples"
    )

    def get_daily_aggregates_for_controller(
        self, passkey_hash: str, controller_id: str, days: int = 7
    ) -> Optional[List[Tuple]]:
        """Aggregats min/max/moyenne par jour sur les ``days`` derniers jours.

        Retourne une liste de tuples (cf. ``AGGREGATE_COLUMNS``), plus recent
        en premier. None si le controller n'appartient pas a l'utilisateur.
        """
        if not self.user_owns_controller(passkey_hash, controller_id):
            return None
        days = max(1, min(days, 365))
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    DATE(timestamp)        AS day,
                    AVG(temperature), MIN(temperature), MAX(temperature),
                    AVG(humidity),    MIN(humidity),    MAX(humidity),
                    AVG(luminosity),  MIN(luminosity),  MAX(luminosity),
                    AVG(pressure),    MIN(pressure),    MAX(pressure),
                    COUNT(*)
                FROM readings
                WHERE controller_id = ?
                  AND DATE(timestamp) >= DATE('now', ?)
                GROUP BY DATE(timestamp)
                ORDER BY day DESC
            ''', (controller_id, f"-{days - 1} days"))
            return cursor.fetchall()

    # ------------------------------------------------------------------
    # Retro-compat : les anciennes methodes retournaient une ligne par capteur.
    # On garde les noms pour que les callers et tests externes continuent a
    # fonctionner pendant la bascule. Chaque snapshot est "explose" en 1..4
    # lignes (ctrl, sensor_id, value, timestamp), une par champ non-NULL.
    # ------------------------------------------------------------------

    def get_latest_readings_for_user(self, passkey_hash: str) -> List[Tuple[str, str, float, str]]:
        return _explode_snapshots(self.get_latest_snapshot_for_user(passkey_hash))

    def get_latest_readings_for_controller(
        self, passkey_hash: str, controller_id: str
    ) -> Optional[List[Tuple[str, str, float, str]]]:
        snaps = self.get_latest_snapshot_for_controller(passkey_hash, controller_id)
        if snaps is None:
            return None
        return _explode_snapshots(snaps)

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
