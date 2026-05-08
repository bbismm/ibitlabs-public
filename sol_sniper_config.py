"""
iBitLabs Alpha Config — Hybrid: Mean Reversion + Grid v5.1
Coinbase Futures | Long+Short | 2x leverage
Backtest verified: +206% (SOL -32%) | All 3 regimes PASS | Fees+Funding included
  Trending (up/down): Regime-adaptive mean reversion (relax with-trend, tighten against-trend)
  Sideways: Micro-grid (0.5% spacing, 3 levels, $100/level)
"""

VERSION = "V5.1"  # V5.1=regime-adaptive signals (backtest verified 2026-04-13)

import os
from dataclasses import dataclass, field


@dataclass
class SniperConfig:
    # ── Exchange (Coinbase Advanced Trade — Futures) ──
    exchange_id: str = "coinbase"
    api_key: str = field(default_factory=lambda: os.environ.get("CB_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.environ.get("CB_API_SECRET", "").replace("\\n", "\n"))
    symbol: str = "SLP-20DEC30-CDE"    # SOL PERP on Coinbase Advanced Trade

    # ── Position (original 82.5% config) ──
    leverage: int = 2                  # 2x leverage (original)
    position_pct: float = 0.80         # 80% capital per position (original)
    capital: float = 1000.0            # Initial capital

    # ── Signal params (original mean reversion — backtest 82.2% WR) ──
    signal_timeframe: str = "15m"      # Entry timeframe
    trend_timeframe: str = "1h"        # Trend confirmation
    htf_timeframe: str = "4h"          # Higher timeframe trend filter (4H EMA gate)
    stoch_rsi_long: float = field(default_factory=lambda: float(os.environ.get("SNIPER_STOCH_RSI_LONG", "0.10")))
    stoch_rsi_short: float = field(default_factory=lambda: float(os.environ.get("SNIPER_STOCH_RSI_SHORT", "0.90")))
    bb_period: int = 20
    bb_std: float = 2.0
    volume_mult: float = 1.0           # Volume > avg x this (original)
    ema_fast: int = 8
    ema_slow: int = 21
    trend_tolerance: float = 0.003     # 0.3% EMA tolerance
    momentum_candles: int = 6          # Look back 6 candles (90min on 15m)
    momentum_block_pct: float = 0.025  # Block signal if price moved >2.5% against it
    rsi_long_cap: float = 72.0         # Block long if RSI > this (overbought)
    rsi_short_floor: float = 28.0      # Block short if RSI < this (oversold)
    momentum_cap_pct: float = 0.01     # Block if momentum >1% in signal direction (exhausted)

    # ── BB Squeeze detection ──
    bb_squeeze_threshold: float = 0.015
    bb_squeeze_bonus: bool = True

    # ── VWAP overextension filter ──
    vwap_enabled: bool = False         # Disabled — original didn't have this
    vwap_max_distance_pct: float = 0.025

    # ── 20 EMA proximity filter ──
    ema20_max_distance_pct: float = 0.02

    # ── Adaptive TP/SL by regime ──
    adaptive_tpsl: bool = False        # Disabled — use original fixed TP/SL

    # ── Risk control ──
    tp_pct: float = field(default_factory=lambda: float(os.environ.get("SNIPER_TP_PCT", "999.0")))  # Disabled — trailing only
    sl_pct: float = 0.050              # 5.0% stop loss
    trailing_activate_pct: float = 0.015   # 1.5% activate trailing stop (4/16 sweep)
    trailing_stop_pct: float = 0.005       # 0.5% drawdown to close (4/16 sweep)
    max_hold_seconds: int = 0  # Disabled — let TP/SL/trailing handle exits
    breakeven_hold_seconds: int = 0  # Disabled — mean reversion needs time to revert
    cooldown_seconds: int = 4 * 3600   # SL cooldown 4h

    # ── Fees (Coinbase Futures) ──
    maker_fee: float = 0.0004         # 0.04%
    taker_fee: float = 0.0006         # 0.06%

    # ── Runtime params ──
    scan_interval_seconds: int = 30    # Scan signals every 30s
    price_check_seconds: int = 3       # Check price every 3s
    db_path: str = "sol_sniper.db"

    # ── Regime detection ──
    regime_window_hours: int = 288     # 12 days of 1h candles (Coinbase limit: 350)
    regime_up_threshold: float = 0.02
    regime_down_threshold: float = -0.02

    # ── Strategy identity ──
    strategy_version: str = "hybrid_v5.1"
    strategy_intent: str = "meanrev_grid_hybrid"
    instance_name: str = "live"

    def validate(self):
        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Please set environment variables:\n"
                "export CB_API_KEY='your_key'\n"
                "export CB_API_SECRET='your_secret'"
            )
