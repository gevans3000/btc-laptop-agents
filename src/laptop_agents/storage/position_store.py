import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from laptop_agents.core.logger import logger


class PositionStore:
    """
    SQLite-backed persistence for trading state.
    Uses WAL mode for high concurrency and crash resilience.
    """

    def close(self) -> None:
        """Close any active relationships."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            # WAL mode is persistent, so we only need to set it once theoretically,
            # but setting it on connection ensures it's active.
            conn.execute("PRAGMA journal_mode=WAL;")
            # synchronous=NORMAL is safe for WAL and faster
            conn.execute("PRAGMA synchronous=NORMAL;")

            # Key-Value store for latest state per symbol (snapshot)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state (
                    symbol TEXT PRIMARY KEY,
                    data JSON NOT NULL,
                    updated_at REAL NOT NULL
                )
            """
            )

            conn.commit()
            conn.close()
            logger.info(f"Initialized PositionStore at {self.db_path} (WAL mode)")
        except Exception as e:
            logger.error(f"Failed to initialize PositionStore DB: {e}")
            raise

    def save_state(self, symbol: str, state_data: Dict[str, Any]) -> None:
        """
        Atomically save the full state snapshot for a symbol.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            # Context manager handles commit/rollback
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO state (symbol, data, updated_at) VALUES (?, ?, ?)",
                    (symbol, json.dumps(state_data), time.time()),
                )
            conn.close()
        except Exception as e:
            logger.critical(f"FATAL: Failed to save state to DB: {e}")
            raise

    def load_state(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Load the latest state snapshot for a symbol.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT data FROM state WHERE symbol = ?", (symbol,))
            row = cursor.fetchone()
            conn.close()

            if row:
                return json.loads(row[0])
            return None
        except Exception as e:
            logger.error(f"Failed to load state from DB: {e}")
            return None
