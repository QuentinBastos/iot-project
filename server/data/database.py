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
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    controller_id TEXT NOT NULL,
                    sensor_id TEXT NOT NULL,
                    value REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
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
