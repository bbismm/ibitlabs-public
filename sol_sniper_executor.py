"""
iBitLabs Alpha V3 Executor — Coinbase Futures (SOL PERP)
Single position, long+short, 3x leverage

Open position: limit order (maker fee 0.04%)
Close position: TP/trailing stop use limit | SL/timeout use market (taker fee 0.06%)
"""

import json
import logging
import os
import time
from sol_sniper_config import SniperConfig
from state_db import StateDB

logger = logging.getLogger(__name__)

# State file path is per-instance: live and shadow must not collide.
STATE_FILE = os.environ.get("SNIPER_STATE_FILE", "sol_sniper_state.json")


class SniperExecutor:
    def __init__(self, exchange, config: SniperConfig, db: StateDB):
        self.exchange = exchange
        self.config = config
        self.db = db

        # Current position
        self.position = None  # {symbol, direction, entry_price, quantity, order_id,
        #                        margin, timestamp, reasons}
        self.highest_pnl_pct = 0.0   # MFE (Max Favorable Excursion, decimal)
        self.lowest_pnl_pct = 0.0    # MAE (Max Adverse Excursion, decimal) — added 2026-04-22
        self.trailing_active = False
        # Shadow 12h-rule-B observability (added 2026-04-23). Logs "would have fired"
        # events for hypothetical rule: elapsed>12h AND pnl<0 AND trailing never armed.
        # Zero execution risk — purely a log-only observation. 30-day shadow window
        # will produce the evidence needed to decide whether to ship rule B live.
        # Rule spec + analysis script: docs/shadow_12h_rule.md
        self.shadow_12h_rule_fired = False
        self.shadow_12h_log_path = os.environ.get(
            "SHADOW_12H_LOG", "./logs/shadow_12h_rule.jsonl"
        )

        # Restore previous state for crash recovery
        self._load_state()

    def open_position(self, signal: dict, balance: float) -> bool:
        """
        Open position (long or short)
        signal: {direction, entry_price, reasons, ...}
        """
        cfg = self.config
        symbol = cfg.symbol
        direction = signal["direction"]
        entry_price = signal["entry_price"]

        # balance = Coinbase futures_buying_power (already includes leverage)
        # Do NOT multiply by leverage again — buying_power is the leveraged amount
        spend = balance * cfg.position_pct
        # SOL PERP: each contract = 5 SOL, priced per SOL
        contract_value = entry_price * 5  # $5 * price per contract
        quantity = max(1, int(spend / contract_value))  # Integer contracts

        side = "buy" if direction == "long" else "sell"
        dir_label = "LONG" if direction == "long" else "SHORT"

        logger.info(
            f"[SNIPER OPEN] {dir_label} {symbol} | Amount: ${spend:.2f} | "
            f"Qty: {quantity} | Price: ~{entry_price:.2f}"
        )

        try:
            ticker = self.exchange.fetch_ticker(symbol)

            if direction == "long":
                # Long: slightly above ask to ensure fill
                limit_price = round(ticker["ask"] * 1.001, 2)
                resp = self.exchange.create_limit_order(
                    symbol=symbol, side="buy",
                    amount=quantity, price=limit_price,
                )
            else:
                # Short: slightly below bid to ensure fill
                limit_price = round(ticker["bid"] * 0.999, 2)
                resp = self.exchange.create_limit_order(
                    symbol=symbol, side="sell",
                    amount=quantity, price=limit_price,
                )

            order_id = str(resp["id"])
            # Get actual fill price from exchange (not ticker fallback)
            real_fill = self.exchange.get_order_fill_price(order_id) if order_id else None
            fill_price = real_fill or float(resp.get("average") or resp.get("price") or limit_price)

            # ── Verify position actually exists on exchange before trusting state ──
            # Order 200 response ≠ position confirmed (openclaw-19097 moltbook feedback,
            # 4/16). Coinbase position list has small lag; poll up to 3s.
            verified_qty = None
            verified_side_ok = False
            for attempt in range(6):  # 6 × 500ms = 3s
                time.sleep(0.5)
                try:
                    positions = self.exchange.fetch_positions()
                    for p in positions:
                        if p["symbol"] == symbol and p["contracts"] > 0:
                            verified_qty = p["contracts"]
                            verified_side_ok = (
                                (direction == "long" and p["side"] != "short") or
                                (direction == "short" and p["side"] == "short")
                            )
                            break
                    if verified_qty is not None:
                        break
                except Exception as verify_err:
                    logger.warning(f"[SNIPER VERIFY] fetch_positions attempt {attempt+1} failed: {verify_err}")

            if verified_qty is None:
                # Safety: if order hasn't filled, cancel it so it can't fill
                # later while we think we're flat. If it did fill, cancel is
                # a no-op and the reconciler will pick it up on next restart.
                try:
                    self.exchange.cancel_orders([order_id])
                    logger.warning(f"[SNIPER VERIFY] Cancelled order {order_id} defensively")
                except Exception:
                    pass
                logger.error(
                    f"[SNIPER VERIFY FAIL] Order {order_id} acknowledged but no "
                    f"position found on exchange after 3s. Not updating internal state. "
                    f"Reconciler will resolve on next restart."
                )
                return False
            if not verified_side_ok:
                logger.error(
                    f"[SNIPER VERIFY FAIL] Position direction mismatch: expected {direction}, "
                    f"exchange shows opposite. Not updating state, aborting."
                )
                return False
            if verified_qty != quantity:
                logger.warning(
                    f"[SNIPER VERIFY] Partial fill / size mismatch: requested {quantity}, "
                    f"exchange has {verified_qty}. Using exchange truth."
                )
                quantity = verified_qty

            reasons_list = signal.get("reasons", []) or []
            trigger_rule = " | ".join(str(r) for r in reasons_list) if reasons_list else None
            regime_at_open = signal.get("regime")

            # NOTE: margin=spend kept here for backwards-compat, but is no
            # longer used in PnL calculation as of 2026-04-22. PnL now uses
            # real notional (price × qty × 5) to match actual Coinbase balance
            # movement. See check_position() line ~224 and close_position()
            # line ~357 for the corrected formula. See Notion:
            # "PnL formula fix 2026-04-22" (battle room supplement).
            self.position = {
                "symbol": symbol,
                "direction": direction,
                "entry_price": fill_price,
                "quantity": quantity,
                "order_id": order_id,
                "margin": spend,
                "timestamp": time.time(),
                "reasons": reasons_list,
                "trigger_rule": trigger_rule,
                "regime": regime_at_open,
            }
            self.highest_pnl_pct = 0.0
            self.lowest_pnl_pct = 0.0  # MAE reset for new position
            self.trailing_active = False
            self.shadow_12h_rule_fired = False  # Shadow observability — reset per position

            # Record to DB
            self.db.save_order(
                order_id=order_id,
                symbol=symbol,
                side=side.upper(),
                price=fill_price,
                quantity=quantity,
                grid_index=0,
            )
            # Entry fee — limit/maker on open
            entry_notional_open = fill_price * quantity * 5
            entry_fee_open = entry_notional_open * cfg.maker_fee
            self.db.log_trade(
                symbol, side.upper(), fill_price, quantity,
                fill_price * quantity,
                direction=direction,
                entry_price=fill_price,
                fees=entry_fee_open,
                strategy_version=cfg.strategy_version,
                strategy_intent=cfg.strategy_intent,
                trigger_rule=trigger_rule,
                instance_name=cfg.instance_name,
                regime=regime_at_open,
            )

            logger.info(
                f"[SNIPER FILLED] {dir_label} {symbol} @ {fill_price:.2f} x {quantity} "
                f"| Amount: ${spend:.2f} | ID: {order_id}"
            )
            return True

        except Exception as e:
            logger.error(f"[SNIPER OPEN FAILED] {symbol} {side}: {e}")
            return False

    def check_position(self) -> dict:
        """
        Check current position including TP/SL/trailing stop/timeout
        Returns: {action, reason, pnl_usd, pnl_pct, current_price}
          action: 'hold' | 'close_tp' | 'close_sl' | 'close_trailing' | 'close_timeout'
        """
        if not self.position:
            return {"action": "none"}

        cfg = self.config
        p = self.position

        try:
            ticker = self.exchange.fetch_ticker(p["symbol"])
            current_price = ticker.get("last", 0)
        except Exception as e:
            logger.error(f"[SNIPER] Price fetch failed: {e}")
            return {"action": "hold"}

        # Calculate PnL
        if p["direction"] == "long":
            pnl_pct = (current_price - p["entry_price"]) / p["entry_price"]
        else:
            pnl_pct = (p["entry_price"] - current_price) / p["entry_price"]

        # PnL in USD = price_delta × position_size_in_SOL
        # 1 SOL PERP contract (SLP-*) = 5 SOL. Previously used
        # pnl_pct * p["margin"] which inflated dollar PnL by ~1.77x
        # because margin = balance*position_pct != notional.
        # See Notion: "PnL formula fix 2026-04-22".
        pnl_usd = pnl_pct * p["entry_price"] * p["quantity"] * 5

        result = {
            "action": "hold",
            "reason": "",
            "pnl_usd": pnl_usd,
            "pnl_pct": pnl_pct,
            "current_price": current_price,
        }

        # ── Adaptive TP/SL by regime ──
        regime = p.get("regime", "sideways")
        if cfg.adaptive_tpsl and regime in ("up", "down"):
            tp = cfg.tp_pct_trending
            sl = cfg.sl_pct_trending
        elif cfg.adaptive_tpsl and regime == "sideways":
            tp = cfg.tp_pct_sideways
            sl = cfg.sl_pct_sideways
        else:
            tp = cfg.tp_pct
            sl = cfg.sl_pct

        # ── Take profit ──
        if pnl_pct >= tp:
            result["action"] = "close_tp"
            result["reason"] = f"TP +{pnl_pct:.2%} (${pnl_usd:+.2f}) [regime={regime}]"
            return result

        # ── Stop loss ──
        if pnl_pct <= -sl:
            result["action"] = "close_sl"
            result["reason"] = f"SL {pnl_pct:.2%} (${pnl_usd:+.2f}) [regime={regime}]"
            return result

        # ── Track path extremes (MFE / MAE — added 2026-04-22 for post-hoc analysis) ──
        if pnl_pct > self.highest_pnl_pct:
            self.highest_pnl_pct = pnl_pct
        if pnl_pct < self.lowest_pnl_pct:
            self.lowest_pnl_pct = pnl_pct

        # ── Trailing stop ──

        if pnl_pct >= cfg.trailing_activate_pct and not self.trailing_active:
            self.trailing_active = True
            logger.info(f"[SNIPER TRAILING] Activated! Unrealized +{pnl_pct:.2%}")

        if self.trailing_active:
            drawdown = self.highest_pnl_pct - pnl_pct
            if drawdown >= cfg.trailing_stop_pct:
                result["action"] = "close_trailing"
                result["reason"] = (
                    f"Trailing stop | Peak +{self.highest_pnl_pct:.2%} -> "
                    f"Drawdown {drawdown:.2%} | Locked +{pnl_pct:.2%} (${pnl_usd:+.2f})"
                )
                return result

        # ── Break-even stop (disabled — mean reversion needs time) ──
        elapsed = time.time() - p["timestamp"]
        breakeven_cutoff = getattr(cfg, "breakeven_hold_seconds", 0)
        if breakeven_cutoff > 0:
            # Post-α fix: exits pay taker fee (close_position endpoint is market-only),
            # entries still pay maker. Cushion must cover both legs OR the BE trigger
            # will fire at a point where realized PnL is still slightly negative.
            fee_cushion = self.config.maker_fee + self.config.taker_fee
            if elapsed >= breakeven_cutoff and pnl_pct <= fee_cushion and self.highest_pnl_pct > fee_cushion:
                hours = elapsed / 3600
                result["action"] = "close_trailing"
                result["reason"] = (
                    f"Break-even exit {hours:.1f}h | Peak +{self.highest_pnl_pct:.2%} "
                    f"faded to {pnl_pct:+.2%} (${pnl_usd:+.2f})"
                )
                return result

        # ── Timeout (disabled — mean reversion needs time to revert) ──
        if cfg.max_hold_seconds > 0 and elapsed >= cfg.max_hold_seconds:
            hours = elapsed / 3600
            result["action"] = "close_timeout"
            result["reason"] = f"Timeout {hours:.1f}h | PnL {pnl_pct:+.2%} (${pnl_usd:+.2f})"
            return result

        # ── Shadow rule B: 12h compound time cap (LOG-ONLY, no execution) ──
        # Added 2026-04-23. Observes a hypothetical rule: if position has been open
        # >12h AND still negative AND trailing never armed (highest_pnl_pct < activate
        # threshold), log a "would have fired" event. Does NOT close the position.
        # 30-day shadow window intended to produce evidence before any decision to
        # promote this rule to live execution. See docs/shadow_12h_rule.md for full
        # rationale, Notion decision doc, and analysis script.
        if (
            not self.shadow_12h_rule_fired
            and elapsed >= 12 * 3600
            and pnl_pct < 0
            and self.highest_pnl_pct < cfg.trailing_activate_pct
        ):
            self._log_shadow_12h_rule(p, elapsed, pnl_pct, pnl_usd, current_price)
            self.shadow_12h_rule_fired = True
            # Persist immediately so a crash between fire and next position
            # event doesn't cause a duplicate log line on restart.
            try:
                self._save_state()
            except Exception as e:
                logger.warning(f"[SHADOW-12h-RULE] post-fire state save failed (non-fatal): {e}")
            # intentionally fall through — do NOT close the position

        return result

    def _log_shadow_12h_rule(self, position: dict, elapsed: float,
                              pnl_pct: float, pnl_usd: float,
                              current_price: float) -> None:
        """
        Log a hypothetical shadow-rule-B trigger event. Does NOT execute.

        Rule B spec (observation only, 2026-04-23 → 2026-05-23 window):
            elapsed > 12h AND pnl_pct < 0 AND highest_pnl_pct < trailing_activate_pct

        Writes an append-only JSONL line with a hypothetical "would have closed here"
        snapshot. The actual close of this position (whenever it happens) can be
        joined by entry_ts for post-hoc EV analysis.

        See analysis script: scripts/analyze_shadow_12h_rule.py
        """
        try:
            os.makedirs(os.path.dirname(self.shadow_12h_log_path), exist_ok=True)
            entry = position.get("entry_price")
            qty = position.get("quantity")
            direction = position.get("direction")
            entry_ts = position.get("timestamp")

            # Hypothetical close PnL: taker fee on the forced exit (close_perp_position
            # endpoint is market-only post-α fix). Keep the sign from pnl_pct.
            hypothetical_net_pct = pnl_pct - self.config.taker_fee
            hypothetical_pnl_usd = hypothetical_net_pct * entry * qty * 5

            entry_dict = {
                "schema_version": 1,
                "event": "shadow_12h_rule_fired",
                "fire_ts": time.time(),
                "entry_ts": entry_ts,
                "elapsed_hours": round(elapsed / 3600, 3),
                "direction": direction,
                "entry_price": entry,
                "current_price": current_price,
                "quantity": qty,
                "pnl_pct": round(pnl_pct, 6),
                "pnl_usd_current": round(pnl_usd, 3),
                "hypothetical_close_pnl_usd": round(hypothetical_pnl_usd, 3),
                "highest_pnl_pct": round(self.highest_pnl_pct, 6),  # MFE
                "lowest_pnl_pct": round(self.lowest_pnl_pct, 6),    # MAE
                "trailing_active_at_fire": self.trailing_active,
                "trailing_activate_pct": self.config.trailing_activate_pct,
                "taker_fee": self.config.taker_fee,
                "maker_fee": self.config.maker_fee,
                "strategy_version": getattr(self.config, "strategy_version", "unknown"),
                "symbol": position.get("symbol"),
                "regime_at_open": position.get("regime"),
            }

            with open(self.shadow_12h_log_path, "a") as f:
                f.write(json.dumps(entry_dict) + "\n")

            hours = elapsed / 3600
            logger.info(
                f"[SHADOW-12h-RULE] Would have fired: "
                f"entry={entry} current={current_price} elapsed={hours:.2f}h "
                f"pnl={pnl_pct:+.3%} MFE={self.highest_pnl_pct:+.3%} "
                f"MAE={self.lowest_pnl_pct:+.3%} "
                f"hypothetical_net=${hypothetical_pnl_usd:+.2f} "
                f"| logged to {self.shadow_12h_log_path}"
            )
        except Exception as e:
            # Shadow logging must never break the live executor. Swallow errors.
            logger.warning(f"[SHADOW-12h-RULE] log failed (non-fatal): {e}")

    def close_position(self, reason: str, use_market: bool = False) -> dict:
        """
        Close position
        use_market: True=market(SL/timeout), False=limit(TP/trailing stop)
        Returns: {pnl_usd, pnl_pct, fill_price}
        """
        if not self.position:
            return {"pnl_usd": 0, "pnl_pct": 0}

        p = self.position
        symbol = p["symbol"]
        direction = p["direction"]
        quantity = p["quantity"]
        entry_price = p["entry_price"]

        close_side = "sell" if direction == "long" else "buy"
        dir_label = "Close LONG" if direction == "long" else "Close SHORT"

        try:
            ticker = self.exchange.fetch_ticker(symbol)

            if use_market:
                # Use Coinbase dedicated close_position endpoint.
                # Plain create_market_order on a perp can leave a residual
                # opposite-side position instead of flattening. Root cause
                # of trade #325 (2026-04-19) — see battle room doc. SDK
                # auto-detects direction so side is not passed here.
                resp = self.exchange.close_perp_position(
                    symbol=symbol, size=quantity,
                )
            else:
                # All close paths now use Coinbase dedicated close_position
                # endpoint (which is market-only). Rationale: user may be away
                # from keyboard when an SL/ghost alert fires, so limit close
                # (which could leave a residual opposite position) cannot be
                # the sole guard — even with reconciler alerts.
                # NOTE: use_market parameter is now dead code but preserved
                # for call-site compatibility. Clean up in a future refactor.
                resp = self.exchange.close_perp_position(
                    symbol=symbol, size=quantity,
                )

            # Get actual fill price from exchange (not ticker fallback)
            close_order_id = str(resp.get("id", ""))
            real_fill = self.exchange.get_order_fill_price(close_order_id) if close_order_id else None
            fill_price = real_fill or float(resp.get("average") or resp.get("price") or ticker["last"])

            if direction == "long":
                pnl_pct = (fill_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - fill_price) / entry_price

            # Real USD PnL = price_delta × contract_count × 5 SOL/contract
            # (not pnl_pct * margin — margin=balance*0.80 != notional).
            # Fix 2026-04-22 · see check_position() for the full writeup.
            gross_pnl = pnl_pct * entry_price * quantity * 5

            # ── Fees (SOL PERP: 5 SOL per contract) ──
            # Entry is always limit (maker), close depends on order type
            entry_notional = entry_price * quantity * 5
            exit_notional = fill_price * quantity * 5
            entry_fee = entry_notional * self.config.maker_fee
            # All closes now use market (close_position endpoint) → always taker
            exit_fee = exit_notional * self.config.taker_fee
            total_fee = entry_fee + exit_fee
            pnl_usd = gross_pnl - total_fee

            # Map free-form reason → canonical exit_reason tag
            reason_lc = (reason or "").lower()
            if reason_lc.startswith("tp"):
                exit_reason_tag = "tp"
            elif reason_lc.startswith("sl"):
                exit_reason_tag = "sl"
            elif "break-even" in reason_lc or "breakeven" in reason_lc:
                exit_reason_tag = "breakeven"
            elif "trailing" in reason_lc:
                exit_reason_tag = "trailing"
            elif "timeout" in reason_lc:
                exit_reason_tag = "timeout"
            elif "force" in reason_lc or "exit" in reason_lc:
                exit_reason_tag = "force_close"
            else:
                exit_reason_tag = "other"

            # Record (store net PnL — matches real account delta)
            self.db.update_order_status(p["order_id"], "CLOSED")
            self.db.log_trade(
                symbol, close_side.upper(), fill_price, quantity,
                fill_price * quantity, pnl_usd,
                direction=direction,
                entry_price=entry_price,
                exit_price=fill_price,
                exit_reason=exit_reason_tag,
                fees=total_fee,
                strategy_version=self.config.strategy_version,
                strategy_intent=self.config.strategy_intent,
                trigger_rule=p.get("trigger_rule"),
                instance_name=self.config.instance_name,
                regime=p.get("regime"),
                mfe=self.highest_pnl_pct,  # path max profit (decimal)
                mae=self.lowest_pnl_pct,   # path max drawdown (decimal)
            )

            sign = "+" if pnl_usd >= 0 else ""
            logger.info(
                f"[SNIPER CLOSE] {dir_label} {symbol} @ {fill_price:.2f} | "
                f"Gross: ${gross_pnl:+.2f} | Fee: -${total_fee:.2f} | "
                f"Net: {sign}${pnl_usd:.2f} ({pnl_pct:+.2%}) | {reason}"
            )

            result = {
                "pnl_usd": pnl_usd,
                "pnl_pct": pnl_pct,
                "fill_price": fill_price,
                "direction": direction,
                "entry_price": entry_price,
                "gross_pnl": gross_pnl,
                "fee": total_fee,
                "reason": reason,
                "exit_reason": exit_reason_tag,
            }

            self.position = None
            self.highest_pnl_pct = 0.0
            self.lowest_pnl_pct = 0.0
            self.trailing_active = False
            self.shadow_12h_rule_fired = False  # Shadow observability — reset per position

            return result

        except Exception as e:
            logger.error(f"[SNIPER CLOSE FAILED] {symbol}: {e}")
            return {"pnl_usd": 0, "pnl_pct": 0}

    def force_close(self):
        """Force close (called on exit)"""
        if self.position:
            logger.warning(f"[SNIPER] Force close {self.position['symbol']}")
            return self.close_position("System exit force close", use_market=True)
        return None

    def has_position(self) -> bool:
        return self.position is not None

    def get_balance(self) -> float:
        """Return available margin (real funds, not leveraged buying power)"""
        try:
            bal = self.exchange.fetch_balance()
            # Use available_margin (real funds) instead of buying_power (already leveraged)
            margin = bal.get("info", {}).get("available_margin", 0)
            return float(margin or 0)
        except Exception:
            return 0.0

    def get_position_info(self) -> str:
        if not self.position:
            return "No position"
        p = self.position
        dir_cn = "LONG" if p["direction"] == "long" else "SHORT"
        elapsed = time.time() - p["timestamp"]
        mins = int(elapsed / 60)
        trailing_str = " [TRAIL]" if self.trailing_active else ""
        return (
            f"{dir_cn} {p['symbol']} @ {p['entry_price']:.2f} | "
            f"${p['margin']:.0f} | Hold {mins}min{trailing_str}"
        )

    # ── State persistence (for crash recovery) ──

    def _save_state(self, grid_status=None):
        state = {
            "mode": "live",
            "highest_pnl_pct": self.highest_pnl_pct,
            "lowest_pnl_pct": self.lowest_pnl_pct,  # MAE persistence (added 2026-04-23)
            "trailing_active": self.trailing_active,
            # Shadow rule B fire flag — must be persisted across restarts so a
            # single position doesn't get double-logged after a bot restart.
            "shadow_12h_rule_fired": self.shadow_12h_rule_fired,
            "position": None,
            "grid": grid_status,
        }
        if self.position:
            state["position"] = {
                "symbol": self.position["symbol"],
                "direction": self.position["direction"],
                "entry_price": self.position["entry_price"],
                "quantity": self.position["quantity"],
                "order_id": self.position["order_id"],
                "margin": self.position["margin"],
                "timestamp": self.position["timestamp"],
                "reasons": self.position.get("reasons", []),
                "trigger_rule": self.position.get("trigger_rule"),
                "regime": self.position.get("regime"),
            }
        try:
            tmp = STATE_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, STATE_FILE)
        except Exception:
            pass

    def _load_state(self):
        # Load state file (if any) for trailing/highest_pnl metadata
        saved = None
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    state = json.load(f)
                if state.get("mode") == "live":
                    saved = state
            except Exception:
                pass

        # Always reconcile against real Coinbase position — exchange is source of truth
        real_pos = None
        try:
            real_positions = self.exchange.fetch_positions()
            for rp in real_positions:
                if rp["symbol"] == self.config.symbol and rp["contracts"] > 0:
                    real_pos = rp
                    break
        except Exception as e:
            logger.warning(f"[SNIPER] Could not fetch live position on startup: {e}")

        if real_pos is None:
            # No real position on exchange — discard any stale state file position
            if saved and saved.get("position"):
                logger.warning(
                    f"[SNIPER] State file had a position but Coinbase shows none — "
                    f"discarding stale state"
                )
            self.position = None
            self.highest_pnl_pct = 0.0
            self.lowest_pnl_pct = 0.0
            self.trailing_active = False
            self.shadow_12h_rule_fired = False  # Shadow observability — reset per position
            self._save_state()
            return

        # Real position exists — use exchange truth for entry/quantity/direction
        direction = "short" if real_pos["side"] == "short" else "long"
        real_entry = float(real_pos["entry_price"])
        real_qty = real_pos["contracts"]

        saved_pos = (saved or {}).get("position") or {}
        saved_matches = (
            saved_pos.get("direction") == direction
            and abs(float(saved_pos.get("entry_price", 0)) - real_entry) < 0.01
            and saved_pos.get("quantity") == real_qty
        )

        if saved_matches:
            # State file aligns with exchange — preserve trailing metadata
            self.position = saved_pos
            self.highest_pnl_pct = saved.get("highest_pnl_pct", 0)
            self.lowest_pnl_pct = saved.get("lowest_pnl_pct", 0)  # MAE (added 2026-04-23)
            self.trailing_active = saved.get("trailing_active", False)
            # Shadow rule B fire flag: preserve across restarts so one position
            # doesn't get double-logged (added 2026-04-23).
            self.shadow_12h_rule_fired = saved.get("shadow_12h_rule_fired", False)
            logger.info(f"[SNIPER] Restored live position: {self.get_position_info()}")
        else:
            # State file stale or missing — rebuild from exchange, reset trailing
            if saved_pos:
                logger.warning(
                    f"[SNIPER] State file position ({saved_pos.get('direction')} "
                    f"@ {saved_pos.get('entry_price')}) does not match Coinbase "
                    f"({direction} @ {real_entry:.2f}) — using exchange truth"
                )
            self.position = {
                "symbol": real_pos["symbol"],
                "direction": direction,
                "entry_price": real_entry,
                "quantity": real_qty,
                "order_id": "recovered",
                # Margin = notional / leverage? No — margin here is the notional
                # used for pnl_usd = pnl_pct * margin. Use entry_price * contracts * 5
                # (SOL PERP: 5 SOL per contract)
                "margin": real_entry * real_qty * 5,
                "timestamp": time.time(),
                "reasons": ["recovered from exchange"],
                "trigger_rule": "recovered_from_exchange",
            }
            self.highest_pnl_pct = 0.0
            self.lowest_pnl_pct = 0.0
            self.trailing_active = False
            self.shadow_12h_rule_fired = False  # Shadow observability — reset per position
            logger.info(
                f"[SNIPER] Recovered {direction.upper()} from Coinbase: "
                f"{real_qty} contracts @ ${real_entry:.2f} "
                f"(unrealized PnL: ${real_pos.get('unrealized_pnl', 0):.2f})"
            )
            self._save_state()

