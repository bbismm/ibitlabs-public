"""
iBitLabs paper bot quickstart — runs a full trade lifecycle on mock data.

No live orders. No real money. No Coinbase API key. ~30 seconds runtime.

Demonstrates the SniperExecutor lifecycle:
    open  → tick (no change) → tick (trailing armed) → tick (trailing fires) → close

Inspect the resulting trade row:
    sqlite3 paper_quickstart.db 'SELECT * FROM trade_log;'

See STARTER.md for the full walkthrough.
"""
import os
import time
import logging

from sol_sniper_config import SniperConfig
from sol_sniper_executor import SniperExecutor
from state_db import StateDB

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("quickstart")


class MockExchange:
    """Minimal in-memory exchange supporting the methods SniperExecutor calls.

    Simulates fills against a hard-coded price path. No network calls.

    Methods implemented (matches the surface SniperExecutor exercises):
        fetch_ticker, fetch_positions, fetch_balance,
        create_limit_order, close_perp_position,
        get_order_fill_price, cancel_orders
    """

    def __init__(self, symbol, price_path, starting_balance=1000.0):
        self.symbol = symbol
        self.price_path = price_path
        self.tick_idx = 0
        self.next_order_id = 1
        self.position = None  # simulated exchange-side position state
        self.balance = starting_balance

    def current_price(self):
        return self.price_path[min(self.tick_idx, len(self.price_path) - 1)]

    def advance(self):
        self.tick_idx += 1

    # ── methods called by SniperExecutor ──

    def fetch_ticker(self, symbol):
        p = self.current_price()
        return {"bid": p * 0.999, "ask": p * 1.001, "last": p}

    def fetch_positions(self):
        if self.position is None:
            return []
        return [{
            "symbol": self.position["symbol"],
            "contracts": self.position["contracts"],
            "side": self.position["side"],
        }]

    def fetch_balance(self):
        return {"futures_buying_power": self.balance, "USD": self.balance}

    def create_limit_order(self, symbol, side, amount, price):
        oid = f"mock-{self.next_order_id}"
        self.next_order_id += 1
        # Simulate immediate fill at the requested price
        self.position = {
            "symbol": symbol,
            "contracts": amount,
            "side": "long" if side == "buy" else "short",
        }
        return {"id": oid, "average": price, "price": price}

    def close_perp_position(self, symbol, size):
        oid = f"mock-close-{self.next_order_id}"
        self.next_order_id += 1
        fill = self.current_price()
        self.position = None
        return {"id": oid, "average": fill, "price": fill}

    def get_order_fill_price(self, order_id):
        return self.current_price()

    def cancel_orders(self, order_ids):
        pass


def main():
    log.info("[QUICKSTART] Starting iBitLabs paper bot demo")
    cfg = SniperConfig()
    log.info(f"[QUICKSTART] Loaded config: {cfg.strategy_version}, capital=${cfg.capital}")

    # Use quickstart-specific files so we don't collide with any live bot state
    db = StateDB("paper_quickstart.db")
    os.environ["SNIPER_STATE_FILE"] = "paper_quickstart_state.json"

    # Price path crafted to demonstrate the trailing stop:
    #   tick 0: $100.00  → open here
    #   tick 1: $100.00  → check_position, no change, hold
    #   tick 2: $102.00  → +2.0%, trailing arms (activate threshold = 1.5%)
    #   tick 3: $101.00  → drawdown 1.0% from peak, trailing fires (threshold = 0.5%)
    price_path = [100.00, 100.00, 102.00, 101.00]
    mock = MockExchange(cfg.symbol, price_path, starting_balance=cfg.capital)

    executor = SniperExecutor(mock, cfg, db)

    # Hand-crafted signal — in production, sol_sniper_signals.py generates these
    # from real market data. For the quickstart we just supply one.
    signal = {
        "direction": "long",
        "entry_price": 100.00,
        "reasons": ["mock_signal_for_quickstart"],
        "regime": "sideways",
    }
    log.info(f"[QUICKSTART] Feeding mock LONG signal at ${signal['entry_price']:.2f}")

    if not executor.open_position(signal, balance=cfg.capital):
        log.error("[QUICKSTART] open_position returned False — see logs above")
        return

    # Tick through the price path manually. In production, sol_sniper_main.py
    # loops calling check_position every few seconds; we drive it by hand here.
    for i in range(1, len(price_path)):
        mock.advance()
        price_now = mock.current_price()
        result = executor.check_position()
        action = result.get("action", "hold")

        if action == "hold":
            armed = " [TRAILING ARMED]" if executor.trailing_active else ""
            log.info(f"[QUICKSTART] Tick {i}: price=${price_now:.2f} — hold{armed}")
        else:
            log.info(f"[QUICKSTART] Tick {i}: price=${price_now:.2f} — action={action}")
            close_result = executor.close_position(result.get("reason", "trailing"))
            log.info(f"[QUICKSTART] Closed. PnL: ${close_result.get('pnl_usd', 0):+.2f}")
            break

        time.sleep(0.5)

    log.info("[QUICKSTART] Done.")
    log.info("[QUICKSTART] Inspect the trade row:")
    log.info("    sqlite3 paper_quickstart.db 'SELECT direction, entry_price, exit_price, fees, pnl, exit_reason FROM trade_log;'")


if __name__ == "__main__":
    main()
