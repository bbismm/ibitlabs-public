"""
状态管理 — SQLite持久化
订单状态、冷却记录、成交日志
支持断电恢复
"""

import sqlite3
import time
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class StateDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_tables()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @contextmanager
    def _tx(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_tables(self):
        with self._tx() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS grid_orders (
                    order_id    TEXT PRIMARY KEY,
                    symbol      TEXT NOT NULL,
                    side        TEXT NOT NULL,
                    price       REAL NOT NULL,
                    quantity    REAL NOT NULL,
                    status      TEXT DEFAULT 'NEW',
                    grid_index  INTEGER,
                    created_at  REAL DEFAULT (strftime('%s','now')),
                    updated_at  REAL DEFAULT (strftime('%s','now'))
                );

                CREATE TABLE IF NOT EXISTS cooldowns (
                    symbol      TEXT PRIMARY KEY,
                    start_time  REAL NOT NULL,
                    end_time    REAL NOT NULL,
                    reason      TEXT
                );

                CREATE TABLE IF NOT EXISTS trade_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol      TEXT NOT NULL,
                    side        TEXT NOT NULL,
                    price       REAL NOT NULL,
                    quantity    REAL NOT NULL,
                    usdt_value  REAL,
                    pnl         REAL DEFAULT 0,
                    timestamp   REAL DEFAULT (strftime('%s','now'))
                );
            """)
            self._migrate_trade_log(conn)

    def _migrate_trade_log(self, conn):
        """
        Idempotent schema extension for first-class strategy intent fields.
        Safe to run on every startup. New columns default NULL on historical rows.

        Added fields (Apr 2026):
          direction        — "long" / "short" (position direction, not order side)
          entry_price      — fill price at position open
          exit_price       — fill price at position close (for closes)
          exit_reason      — "tp" / "sl" / "trailing" / "breakeven" / "timeout"
          fees             — round-trip fees in USD (entry + exit)
          funding          — accumulated funding cost in USD
          strategy_version — e.g. "breakout_v3.4"
          strategy_intent  — e.g. "momentum_breakout" / "mean_reversion" / "grid"
          trigger_rule     — human-readable trigger description
          instance_name    — "live" / "shadow" / "paper" — for multi-instance attribution

        Added (Apr 10, 2026) for regime-mismatch diagnostics:
          regime           — "up" / "down" / "sideways" snapshot at the moment of
                             the decision (open OR close — whichever this row is)
        """
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(trade_log)").fetchall()}
        new_cols = [
            ("direction", "TEXT"),
            ("entry_price", "REAL"),
            ("exit_price", "REAL"),
            ("exit_reason", "TEXT"),
            ("fees", "REAL"),
            ("funding", "REAL"),
            ("strategy_version", "TEXT"),
            ("strategy_intent", "TEXT"),
            ("trigger_rule", "TEXT"),
            ("instance_name", "TEXT"),
            ("regime", "TEXT"),
        ]
        for name, sqltype in new_cols:
            if name not in existing:
                conn.execute(f"ALTER TABLE trade_log ADD COLUMN {name} {sqltype}")
                logger.info(f"[StateDB] migrated trade_log: added column {name} {sqltype}")

    # ── 订单管理 ──

    def save_order(self, order_id: str, symbol: str, side: str,
                   price: float, quantity: float, grid_index: int):
        with self._tx() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO grid_orders "
                "(order_id, symbol, side, price, quantity, grid_index, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (order_id, symbol, side, price, quantity, grid_index, time.time())
            )

    def update_order_status(self, order_id: str, status: str):
        with self._tx() as conn:
            conn.execute(
                "UPDATE grid_orders SET status=?, updated_at=? WHERE order_id=?",
                (status, time.time(), order_id)
            )

    def get_active_orders(self, symbol: str = None) -> list:
        with self._tx() as conn:
            if symbol:
                rows = conn.execute(
                    "SELECT * FROM grid_orders WHERE status='NEW' AND symbol=?",
                    (symbol,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM grid_orders WHERE status='NEW'"
                ).fetchall()
            return [dict(r) for r in rows]

    def clear_orders(self, symbol: str):
        with self._tx() as conn:
            conn.execute(
                "UPDATE grid_orders SET status='CANCELLED', updated_at=? WHERE symbol=? AND status='NEW'",
                (time.time(), symbol)
            )

    # ── 冷却管理 ──

    def set_cooldown(self, symbol: str, duration_hours: float, reason: str = "stop_loss"):
        now = time.time()
        end = now + duration_hours * 3600
        with self._tx() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cooldowns (symbol, start_time, end_time, reason) "
                "VALUES (?, ?, ?, ?)",
                (symbol, now, end, reason)
            )
        logger.warning(f"[冷却] {symbol} 进入 {duration_hours}h 冷却期, 原因: {reason}")

    def is_cooling(self, symbol: str) -> bool:
        with self._tx() as conn:
            row = conn.execute(
                "SELECT end_time FROM cooldowns WHERE symbol=?", (symbol,)
            ).fetchone()
            if row and row["end_time"] > time.time():
                return True
            if row:
                conn.execute("DELETE FROM cooldowns WHERE symbol=?", (symbol,))
            return False

    def get_all_cooling(self) -> list:
        now = time.time()
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT symbol, end_time FROM cooldowns WHERE end_time > ?", (now,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ── 交易日志 ──

    def log_trade(self, symbol: str, side: str, price: float,
                  quantity: float, usdt_value: float, pnl: float = 0,
                  *,
                  direction: str = None,
                  entry_price: float = None,
                  exit_price: float = None,
                  exit_reason: str = None,
                  fees: float = None,
                  funding: float = None,
                  strategy_version: str = None,
                  strategy_intent: str = None,
                  trigger_rule: str = None,
                  instance_name: str = None,
                  regime: str = None,
                  mfe: float = None,
                  mae: float = None):
        """
        Persist a trade. The first six positional args preserve the legacy
        signature for grid module compatibility. All strategy-intent fields
        are keyword-only and optional — historical writers keep working,
        new writers populate them.

        mfe / mae: Max Favorable / Adverse Excursion — the highest and lowest
        pnl_pct seen during the life of the position (decimal, e.g. 0.015 = 1.5%).
        Written only on exit rows; NULL on entry rows. Added 2026-04-22 to
        support future Tier 1 BE / max_hold / soft-cap analysis.
        """
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO trade_log (
                    symbol, side, price, quantity, usdt_value, pnl,
                    direction, entry_price, exit_price, exit_reason,
                    fees, funding, strategy_version, strategy_intent,
                    trigger_rule, instance_name, regime, mfe, mae
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (symbol, side, price, quantity, usdt_value, pnl,
                 direction, entry_price, exit_price, exit_reason,
                 fees, funding, strategy_version, strategy_intent,
                 trigger_rule, instance_name, regime, mfe, mae)
            )

    def get_total_pnl(self) -> float:
        with self._tx() as conn:
            row = conn.execute("SELECT COALESCE(SUM(pnl), 0) as total FROM trade_log").fetchone()
            return row["total"]

    def get_active_symbols(self) -> list:
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM grid_orders WHERE status='NEW'"
            ).fetchall()
            return [r["symbol"] for r in rows]
