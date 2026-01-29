import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, cast
from laptop_agents.core.logger import logger


class TradeRepository:
    """
    SQLite-backed persistence for trading state, orders, and fills.
    Uses WAL mode for high concurrency and crash resilience.
    """

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")

            # 1. Orders table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    qty REAL NOT NULL,
                    order_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    price REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """
            )

            # 2. Fills table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fills (
                    fill_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    fill_price REAL NOT NULL,
                    fill_qty REAL NOT NULL,
                    fee REAL NOT NULL,
                    filled_at REAL NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES orders(order_id)
                )
            """
            )

            # 3. Positions table (Current State)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    side TEXT,
                    qty REAL DEFAULT 0,
                    avg_entry REAL,
                    unrealized_pnl REAL,
                    updated_at REAL NOT NULL
                )
            """
            )

            # 4. Session log table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload JSON,
                    logged_at REAL NOT NULL
                )
            """
            )

            # Legacy state table for compatibility with PositionStore
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
            logger.info(f"Initialized TradeRepository at {self.db_path} (WAL mode)")
        except Exception as e:
            logger.error(f"Failed to initialize TradeRepository DB: {e}")
            raise

    # --- Orders ---
    def save_order(self, order_data: Dict[str, Any]) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            now = time.time()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO orders
                    (order_id, symbol, side, qty, order_type, status, price, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        order_data["order_id"],
                        order_data["symbol"],
                        order_data["side"],
                        order_data["qty"],
                        order_data["order_type"],
                        order_data["status"],
                        order_data.get("price"),
                        order_data.get("created_at", now),
                        now,
                    ),
                )
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save order to DB: {e}")

    # --- Fills ---
    def save_fill(self, fill_data: Dict[str, Any]) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO fills
                    (fill_id, order_id, symbol, fill_price, fill_qty, fee, filled_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        fill_data["fill_id"],
                        fill_data["order_id"],
                        fill_data["symbol"],
                        fill_data["fill_price"],
                        fill_data["fill_qty"],
                        fill_data["fee"],
                        fill_data.get("filled_at", time.time()),
                    ),
                )
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save fill to DB: {e}")

    # --- Positions ---
    def save_position(self, symbol: str, pos_data: Dict[str, Any]) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO positions
                    (symbol, side, qty, avg_entry, unrealized_pnl, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        symbol,
                        pos_data.get("side"),
                        pos_data.get("qty", 0),
                        pos_data.get("avg_entry"),
                        pos_data.get("unrealized_pnl"),
                        time.time(),
                    ),
                )
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save position to DB: {e}")

    def load_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM positions WHERE symbol = ?", (symbol,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Failed to load position from DB: {e}")
            return None

    # --- Session Log ---
    def log_session_event(
        self, session_id: str, event_type: str, payload: Dict[str, Any]
    ) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            with conn:
                conn.execute(
                    "INSERT INTO session_log (session_id, event_type, payload, logged_at) VALUES (?, ?, ?, ?)",
                    (session_id, event_type, json.dumps(payload), time.time()),
                )
            conn.close()
        except Exception as e:
            logger.error(f"Failed to log session event to DB: {e}")

    # --- Legacy Compatibility ---
    def save_state(self, symbol: str, state_data: Dict[str, Any]) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
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
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT data FROM state WHERE symbol = ?", (symbol,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return cast(Dict[str, Any], json.loads(row[0]))
            return None
        except Exception as e:
            logger.error(f"Failed to load state from DB: {e}")
            return None
