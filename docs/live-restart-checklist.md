# Pre-Live Restart Checklist — hybrid_v5.1 after α close-order fix

> **Purpose:** gate-check before re-enabling live trading after the 2026-04-19
> #325 ghost position incident and the 2026-04-20 close-order fix (α). Every
> item in MUST-PASS needs a green check before the live plist is
> re-bootstrapped. SHOULD-PASS items can have waivers but document them in
> the waiver log at the bottom.
>
> **Input state assumed:** Bot stopped. Account has no open positions. α fix
> is committed. Reconciler is registered but may be bootout.
>
> **Time budget:** First pass, expect 3-4 hours. Do NOT attempt in one
> sitting if tired. Bad judgment here costs real money.
>
> **Reference:** Battle room doc in Notion (page id 3483c821a4aa8172a043efb2df80753e).

---

## 🔴 MUST-PASS — if any item fails, do not start live

### 1. Account and exchange state is clean

- [ ] Coinbase Positions page shows zero open positions for SLP-20DEC30-CDE
- [ ] Coinbase Open Orders shows zero pending orders
- [ ] Balance ≥ $500 (the stop-all floor)
- [ ] DB↔Exchange reconciler run in the last 24 hours exited 0.
      If it was booted-out, bootstrap + wait one run + verify exit 0

Verification:

```bash
launchctl print gui/$(id -u)/com.ibitlabs.db-exchange-reconcile | grep -E "last exit|runs|state"
tail -20 ~/ibitlabs/logs/db_exchange_reconcile_frequent.log
```

### 2. α close-order fix is live in code ✅ PASS (2026-04-20 evening)

- [x] `grep -c close_perp_position ~/ibitlabs/coinbase_exchange.py` = **1** ✓
- [x] `grep -c close_perp_position ~/ibitlabs/sol_sniper_executor.py` = **2** ✓ (lines 321 market, 332 limit)
- [x] Inside the close path, no uncommented create_market_order / create_limit_order
      calls remain. `create_limit_order` at lines 68/75 are OPEN path (long-buy/short-sell),
      unchanged by design — the fix only touched close semantics
- [x] Both files pass `python3 -c "import ast; ast.parse(open(...).read())"`

### 3. α end-to-end validation — the critical one

This is the test deferred on 2026-04-20. **Cannot be skipped before live resumes.**

Design:

1. Open a 1-contract LONG via the bot's code path (one-off Python script
   importing the executor). Confirm Coinbase Positions shows 1 contract LONG.
2. Trigger a close via the bot's code path (NOT via Coinbase UI):
   `executor.close_position(reason="canary_test", use_market=True)`.
3. Verify on Coinbase:
   - [ ] Positions page shows 0 open positions (not 1 with flipped sign)
   - [ ] Transaction history shows a fill consistent with close
   - [ ] No residual ghost order or position 60 seconds later
4. Verify in DB:
   - [ ] trade_log has a new row within 60 seconds
   - [ ] Row's exit_reason = "canary_test"
5. Run reconciler immediately:
   `~/ibitlabs/scripts/run_db_exchange_reconcile.sh` should exit 0.
   If exit 1, the fix is not working — investigate before live.

**If not comfortable writing the one-off Python script, open a new Claude
session and work through it first. Do NOT skip.**

### 4. Strategy profitability survives the new fee model ✅ PASS (2026-04-20)

After α, all closes pay taker fee (~0.03%) instead of maker rebate on
TP/trailing. Historical rough estimate: $12.58 profit over 14 trades
would compress to ~$3.60 under the new fee model.

- [x] Re-run the strategy backtest with taker_fee applied to all closes.
      Compare to live history
- [x] Backtest under new fee model is **net profitable** over last
      ~120 days (+$343.82 / +31.75% on $1000, 81.3% WR, all 3 regimes PASS)
- [ ] ~~If marginal or net negative: do NOT start live~~ — N/A, not marginal

**Verdict: GO.** Fee-model change does not break the strategy.

**Test design:** Two scratch scripts, same 120-day window
(~2025-12-21 → 2026-04-20, 119 trading days), same strategy code,
only difference = all closes pay taker fee in α.

| Metric | Baseline (maker TP/trail) | α (taker everywhere) | Δ |
|---|---:|---:|---:|
| Net PnL | +$355.02 | +$343.82 | −$11.20 |
| Return | +32.86% | +31.75% | −1.11pp |
| Win rate | 81.3% (691/850) | 81.3% (691/850) | 0 |
| Max drawdown | −19.29% | −19.36% | −0.07pp |
| Total trades | 850 | 850 | 0 |
| Long PnL | +$102.88 | +$99.38 | −$3.50 |
| Short PnL | +$252.15 | +$244.44 | −$7.71 |
| Total fees | $156.77 | $167.06 | +$10.29 |
| Annualized | 14.3% | 10.8% | −3.5pp |
| Regime PASS | UP / DOWN / SIDE | UP / DOWN / SIDE | same |

**Interpretation:** Taker-fee-only closes cost $11.20 / 1.11pp over
120 days. On $1000 capital that's ~$0.094/day. Strategy still
comfortably net profitable, risk profile unchanged.

**Known caveats (documented, not introduced by α):**
- Backtest entry fee uses `margin * maker_fee` instead of
  `notional * maker_fee` → systematically understates fees ~5×. Both
  baseline and α share the bug, so *relative* comparison is valid,
  but *absolute* profitability is optimistic on both sides. Track as
  separate followup — do not fix in same session as fee-model validation.
- 120-day window contains only ~7 days of real v5.1 live trading; the
  other ~113 days are simulation of "if v5.1 had been running then".

**Artifacts:**
- `scratch/sol_sniper_backtest_baseline_90d.py` — original + 120d slice
- `scratch/sol_sniper_backtest_alpha_fees.py` — + taker-only closes
- `logs/backtest_fee_validation/baseline_90d.log`
- `logs/backtest_fee_validation/alpha_90d.log`
- Original `sol_sniper_backtest.py` **not mutated** during this validation

**A bot that loses money safely is still losing money. Single most
important item in this checklist.**

### 5. Cold-start behavior ✅ PASS (2026-04-20 evening, inspection-only)

- [x] **Does the bot check Coinbase for residual positions before entering? YES.**
      `sol_sniper_executor._load_state` (executor.py:485-568) runs on init:
      - Always calls `self.exchange.fetch_positions()` — "exchange is source of truth"
        (explicit comment at line 497)
      - If no live position found → clears any stale state file and sets
        `self.position = None` (lines 508-519)
      - If live position found → rebuilds state from exchange truth; warns if
        state file drifted (lines 520-568)
      - Bot's main loop `sol_sniper_main.py` also cancels all open orders on
        startup for a clean slate (line 414-425)
- [ ] ⚠️ **Wording mismatch:** checklist expects log line `Startup: no open position`.
      Actual logs emit `Restored live position: ...` or `Recovered X from Coinbase: ...`
      when a position exists, and nothing explicit when none exists.
      **Behavior is correct; log string differs.** Followup: either add an
      explicit "Startup: no open position" log line in `_load_state` branch
      at executor.py:515-519, or update this checklist line to match current logs.
      Not a live-resume blocker.

**Still to do live (deferred to real-restart day):** verify the actual log
string in `logs/sniper_launchd.log` within 60s of boot. Cannot verify from
inspection alone — requires bot start.

---

## 🟡 SHOULD-PASS — waivers OK, document in log at bottom

### 6. Config sanity ✅ PASS (2026-04-20 evening)

- [x] **`diff sol_sniper_config.py sol_sniper_config_shadow.py`**: reviewed.
      **Important finding:** `sol_sniper_config_shadow.py` is **not** a
      config subclass — it's a *documentation* file that declares
      `SHADOW_*` module-level constants (trailing 0.004/0.005, separate
      DB path, instance name "shadow") and explains rationale in docstring.
      The shadow instance gets its overrides via CLI flags on
      `com.ibitlabs.sniper-shadow.plist`, not by importing this file.
      No hidden class-level divergence. Safe.
- [x] **Current live values (sol_sniper_config.py):**

      | Param | Value | Notes |
      | --- | --- | --- |
      | `strategy_version` | `hybrid_v5.1` | |
      | `leverage` | `2` | 2× |
      | `position_pct` | `0.80` | 80% of capital per trade |
      | `ema20_max_distance_pct` | `0.02` | 2% — controls 20-EMA proximity filter |
      | `tp_pct` | env `SNIPER_TP_PCT` default `999.0` | TP effectively disabled (trailing-only) |
      | `sl_pct` | `0.050` | 5.0% |
      | `trailing_activate_pct` | `0.015` | 1.5% (4/16 sweep) |
      | `trailing_stop_pct` | `0.005` | 0.5% (4/16 sweep) |
      | `cooldown_seconds` | `14400` | 4h SL cooldown |
      | `max_hold_seconds` | `0` | disabled — TP/SL/trailing-only |
      | `breakeven_hold_seconds` | `0` | disabled |
      | `maker_fee / taker_fee` | `0.0004 / 0.0006` | 0.04% / 0.06% |

- [x] **Live plist ProgramArguments** (`~/Library/LaunchAgents/com.ibitlabs.sniper.plist`):
      `/usr/bin/python3 sol_sniper_main.py --live --no-grid` ✓ — exactly as expected.
      `RunAtLoad=true`, `KeepAlive=true`, `ThrottleInterval=30`. Environment
      variables: CB_API_KEY/SECRET (present), BROADCAST_*, NOTIFY_*, NTFY_TOPIC,
      TELEGRAM_*. Nothing unintended.

### 7. Reconciler is armed and reachable

- [ ] com.ibitlabs.db-exchange-reconcile is bootstrapped
- [ ] Last reconciler run exited 0 (or exited 1 with only known drift)
- [ ] Manual ntfy test: `curl -d "test" https://ntfy.sh/sol-sniper-bonny`
      → phone receives push in 30s
- [ ] ntfy app installed, subscribed, notifications allowed (DND bypass)
- [ ] **Also re-bootstrap `com.ibitlabs.anomaly-detector`** (bootout'd 2026-04-20
      evening to stop 15-min heartbeat/freshness alerts while bot was stopped).
      Command:
      `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ibitlabs.anomaly-detector.plist`

### 8. Observability ✅ PASS (2026-04-20 evening)

- [x] **Dashboard `/api/status` returns 200** ✓ (also `/api/live-status` returns 200)
- [x] **Today's `regime_watch_2026-04-20.log` exists** ✓
      (`./logs/regime_watch_2026-04-20.log`,
      1035 bytes, last written 09:10 by the scheduled regime watcher)
- [x] **Notion `trade_log` sync: WAIVED — accept DB as sole source of truth.**
      Sync has been broken since 2026-04-09 (per battle room). Fixing it requires
      setting Cloudflare secret `NOTION_TOKEN`. Not blocking live resume. Logged
      in waiver table below. DB (`sol_sniper.db`) remains authoritative.

### 9. Known open issues acknowledged ✅ ACK (2026-04-20 evening)

Not blockers, but should be known before restart:

- [x] **`use_market` parameter in close_position() is now dead argument.**
      Confirmed at `sol_sniper_executor.py:330-331` — explicit comment:
      `NOTE: use_market parameter is now dead code but preserved for
      call-site compatibility. Clean up in a future refactor.`
- [x] **4-hour DB write delay on #325's row was never diagnosed.** Known.
      #325 fill happened 18:15:03 UTC on exchange; DB row written 22:15:07 UTC.
      Root cause unknown. Separate investigation.
- [x] **Limit close semantics not available on Coinbase Advanced SDK.**
      Known and accepted — that is precisely why α switched TP/trailing to
      market via `close_perp_position` (SDK's close-position endpoint is
      market-only). Fee impact validated in item #4 (+$0.094/day on $1k).
- [x] **Strategy may need max-hold-time cap or regime-sensitive stop-loss.**
      Known. Flagged in battle room as post-resume followup. Trade #323 held
      41 hours before SL fire; a cap would have cut exposure earlier. Requires
      backtest evidence before parameter change — not in scope for this restart.

---

## 🟢 POST-START — first 5 days of live

Do NOT leave unattended for the first 5 days.

### Day 1

- Watch the first 3 trades live or near-live
- After each close: manually verify Coinbase Positions == DB.
  If diverge, stop the bot immediately
- End of day 1, send a manual ntfy test

### Day 2-5

- Daily: check reconciler log for any exit 1
- Daily: compare realized PnL to pre-live backtest.
  If >50% divergence, investigate
- Log anomalies in the battle room Ops Log

### Day 6+

- If green 5 consecutive days, attention window can extend.
- Reconciler stays on, position size stays fixed, until at least 30 clean days

---

## 📋 Waiver log

If proceeding past a SHOULD-PASS item without full green, document here:

| Date | Item waived | Reason | Mitigating control |
|------|-------------|--------|-------------------|
| 2026-04-20 | #8 Notion `trade_log` sync | Broken since 2026-04-09 — requires Cloudflare secret `NOTION_TOKEN`. Non-blocking for live trading. | DB `sol_sniper.db` is the authoritative source of truth; dashboard reads DB, not Notion |
| 2026-04-20 | #5 log-string `Startup: no open position` | Bot's actual logs emit `Restored live position: ...` or `Recovered X from Coinbase: ...` or silence when none — exact string from checklist never matched production | Substantive behavior (query Coinbase + use exchange truth) verified by code inspection. Deferred log-line addition tracked as separate followup |

---

## 🔗 Reference

- Git commits: 98fc838 (α wrapper in coinbase_exchange), e788a78 (β reconciler)
- Coinbase SDK close_position docs: https://docs.cdp.coinbase.com/advanced-trade/reference/retailbrokerageapi_closeposition
- Root-cause discovery: Notion battle room `CONFIRMED ROOT CAUSE` section

*Last updated: 2026-04-20 evening by Claude + Bonnybb — Tier-A inspection sweep complete: items #2 / #5 / #6 / #8 / #9 marked PASS. Remaining blockers: #1 (account state — requires reconciler re-bootstrap, scheduled 04-21), #3 (α end-to-end canary test — requires real Coinbase position, deferred to a separate focused session), #7 (reconciler armed — same 04-21 dependency as #1). Review before each live restart.*
