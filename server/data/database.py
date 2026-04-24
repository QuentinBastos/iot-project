import sqlite3
import logging
from contextlib import contextmanager

class Database:
    """Manages raw SQLite connections and schema initialization."""

    def __init__(self, db_path: str = "server_data.db"):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def connection(self):
        """Context manager for sqlite3 connections with PRAGMAs."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode=WAL;")
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            logging.getLogger("Database").error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.connection() as conn:
            cursor = conn.cursor()

            # --- Table ``readings`` : un snapshot par ligne -------------------
            # Ancien schema : (id, controller_id, sensor_id, value, timestamp)
            #   -> une ligne PAR capteur, donc 3-4 lignes par emission radio.
            # Nouveau schema : un instantane multi-capteurs par ligne.
            # Si l'ancien schema est detecte (colonne `sensor_id`), on pivote
            # les anciennes lignes (groupees par controller_id + timestamp) en
            # snapshots, puis on remplace la table.
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='readings'"
            )
            readings_exists = cursor.fetchone() is not None
            legacy_schema = False
            if readings_exists:
                cursor.execute("PRAGMA table_info(readings)")
                cols = {row[1] for row in cursor.fetchall()}
                legacy_schema = "sensor_id" in cols

            if legacy_schema:
                cursor.execute('''
                    CREATE TABLE readings_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        controller_id TEXT NOT NULL,
                        temperature REAL,
                        humidity    REAL,
                        luminosity  REAL,
                        pressure    REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # Pivot en best-effort : un snapshot par (controller_id, timestamp).
                cursor.execute('''
                    INSERT INTO readings_new
                        (controller_id, temperature, humidity, luminosity, pressure, timestamp)
                    SELECT
                        controller_id,
                        MAX(CASE WHEN UPPER(sensor_id) IN ('T','TEMP','TEMPERATURE') THEN value END),
                        MAX(CASE WHEN UPPER(sensor_id) IN ('H','HUM','HUMID','HUMIDITY','HUMIDITE') THEN value END),
                        MAX(CASE WHEN UPPER(sensor_id) IN ('L','LUM','LUMIN','LUMINOSITY','LUMINOSITE') THEN value END),
                        MAX(CASE WHEN UPPER(sensor_id) IN ('P','PRES','PRESSURE','PRESSION') THEN value END),
                        timestamp
                    FROM readings
                    GROUP BY controller_id, timestamp
                ''')
                cursor.execute("DROP TABLE readings")
                cursor.execute("ALTER TABLE readings_new RENAME TO readings")
            else:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS readings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        controller_id TEXT NOT NULL,
                        temperature REAL,
                        humidity    REAL,
                        luminosity  REAL,
                        pressure    REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_readings_ctrl_time "
                "ON readings (controller_id, timestamp DESC)"
            )
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS configurations (
                    controller_id TEXT PRIMARY KEY,
                    display_order TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    passkey_hash TEXT PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_controllers (
                    passkey_hash TEXT NOT NULL,
                    controller_id TEXT NOT NULL,
                    PRIMARY KEY (passkey_hash, controller_id),
                    FOREIGN KEY (passkey_hash) REFERENCES users(passkey_hash)
                )
            ''')
            # Migration douce : recopier depuis l'ancienne table si elle existe
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='user_sensors'"
            )
            if cursor.fetchone():
                cursor.execute('''
                    INSERT OR IGNORE INTO user_controllers (passkey_hash, controller_id)
                    SELECT passkey_hash, sensor_id FROM user_sensors
                ''')
                cursor.execute("DROP TABLE user_sensors")
