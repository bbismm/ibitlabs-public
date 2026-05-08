# Shadow Rule B — 12h compound time-cap observation window

**Started:** 2026-04-23
**Review date:** 2026-05-23 (30-day window)
**Status:** shadow mode (log-only, zero execution risk)

## Why this rule is shadow-mode and not live

The Moltbook auto-scan kept flagging a 12h flat hard-cap as `[SYSTEM CODE — URGENT]`. On 2026-04-22 the flat version was formally reviewed and rejected because:

1. It contradicts the [Exit-Logic Review 2026-04-21](https://www.notion.so/34a3c821a4aa815e9390e5eb26c97265) (approved rule shape is 24h-compound or 36h-flat, paused pending MFE/MAE data)
2. It would kill the 46h slow-mean-reversion winner class (#318 on the live log, +$3.55 trailing exit)
3. It violates the "Record don't restrict" principle

**But.** On 2026-04-23 Bonny (rightly) pushed back: *"did you actually backtest it?"* I had not — the rejection was principle-based. A quick paired-trade replay on v5.1 data showed a *compound* version of the rule (not flat) might be useful:

**Rule B:** `elapsed > 12h AND pnl_pct < 0 AND highest_pnl_pct < trailing_activate_pct (1.5%)`

That's "been open more than 12 hours AND still red AND trailing never armed (was never even green enough to matter)." In the 7-trade v5.1 replay this spares all the winners (including #318's 46h slow reversion) and only fires on positions like #63 that are bleeding without ever going green.

**Problem:** n=7 v5.1 trades. The one clear fire (#325) was a ghost-position-bug loss that the α close-order fix already addressed. We cannot tell from 7 trades whether rule B saves real money on go-forward positions.

**Solution:** 30-day shadow window. Log every hypothetical fire event. Compare to actual close outcomes. Decide on 2026-05-23 based on evidence.

## Shadow instrumentation (what the executor actually does)

`sol_sniper_executor.py` (edited 2026-04-23):

- `SniperExecutor.__init__`: adds `self.shadow_12h_rule_fired = False` + log path config
- 4 position-reset sites: each resets the flag on new/recovered/cleared position
- `check_position`: after the timeout block, evaluates the compound condition each tick. On first fire per position, calls `_log_shadow_12h_rule()` and sets the flag. **Does NOT close the position.** Intentionally falls through.
- `_log_shadow_12h_rule()`: appends a single JSONL line to `logs/shadow_12h_rule.jsonl` with full context (entry/current price, elapsed, pnl, MFE, MAE, hypothetical close PnL net of taker fee, strategy version, regime).
- Errors in the shadow log path are swallowed — shadow instrumentation must never break live execution.

## Analysis

Run the analyzer any time to see current state:

```
python3 ./scripts/analyze_shadow_12h_rule.py
```

The script:
1. Loads `logs/shadow_12h_rule.jsonl`
2. Loads paired closed trades from `sol_sniper.db` (hybrid_v5.1)
3. Joins each shadow fire event to its eventual actual close by `entry_ts`
4. Computes per-trade delta (hypothetical close PnL − actual close PnL)
5. Reports aggregate net EV + interpretation heuristic

`--json` for machine-readable output. `--window-days N` to restrict.

## Decision criteria (2026-05-23 review)

| Signal | Decision |
|--------|----------|
| Net delta **positive** AND ≥10 fire events AND more "rule B better" than "worse" | Promote rule B to live |
| Net delta negative OR rule B worse on majority | Reject. Archive decision record. |
| <5 fire events or inconclusive | Extend shadow window another 30 days |
| Specific failure modes (e.g. rule fires then position recovers) | Refine condition (e.g. tighten pnl threshold, loosen MFE threshold) |

## Alerts / tripwires

- A single shadow-fire is NOT a signal by itself. #63 (live at time of shadow shipping) is almost certain to fire the rule within ~1 hour of this deploy. That's expected — one data point, watched.
- If the shadow fires >5 times in the first 72 hours, that's a signal the rule is over-firing. Recheck MFE threshold — maybe 1.5% is too strict; try 0.5% or breakeven-adjusted.
- If no shadow fires in 30 days, that's also a signal — rule B doesn't actually trigger on post-α trades, meaning we gained clarity for free.

## Related

- Notion decision record: [12h time-cap rule — reviewed, not adopted (2026-04-22)](https://www.notion.so/34b3c821a4aa811090caf22c1c8e9423)
- Canonical rule doc: [Exit-Logic Review + fee_cushion Fix — 2026-04-21](https://www.notion.so/34a3c821a4aa815e9390e5eb26c97265)
- Memory file: `~/.claude/projects/-Users-bonnyagent/memory/feedback_12h_cap_rejected.md`

## Bot restart

This change is inert until the live bot restarts. The shadow instrumentation lives in `sol_sniper_executor.py` and picks up on the next bot invocation. No separate migration or DB schema change required — the JSONL log file is created on first fire.

The running position (#63 as of write-time, 11.2h elapsed, long @ 88.20, −2.54%, trailing never armed) will NOT trigger shadow logging retroactively — it'll only fire if the bot restarts before #63 closes. Whether the user restarts now for immediate instrumentation or waits for a natural restart is an operator call; both are fine. Either way, the 30-day window starts from the first live fire event.
