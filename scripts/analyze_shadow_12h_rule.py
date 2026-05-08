#!/usr/bin/env python3
"""
analyze_shadow_12h_rule.py — Post-hoc analysis of the 12h-compound shadow rule.

Pairs each 'shadow_12h_rule_fired' event (from logs/shadow_12h_rule.jsonl) with
its eventual actual close (from sol_sniper.db trade_log), and computes:

  - How many positions would have triggered the rule
  - Hypothetical close PnL (rule fired) vs actual close PnL (no rule)
  - Net EV delta per trade and in aggregate
  - Win-rate and distribution breakdown

Rule B spec (shadow since 2026-04-23):
  elapsed > 12h AND pnl_pct < 0 AND highest_pnl_pct < trailing_activate_pct

Usage:
  python3 scripts/analyze_shadow_12h_rule.py
  python3 scripts/analyze_shadow_12h_rule.py --window-days 30
  python3 scripts/analyze_shadow_12h_rule.py --log-path custom/path.jsonl --db custom.db
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

DEFAULT_LOG = "./logs/shadow_12h_rule.jsonl"
DEFAULT_DB = "./sol_sniper.db"


def load_shadow_events(log_path):
    """Parse the append-only JSONL shadow log into a list of dicts."""
    if not os.path.exists(log_path):
        return []
    events = []
    with open(log_path) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[warn] line {i}: {e}", file=sys.stderr)
    return events


def load_closed_trades(db_path, strategy_version="hybrid_v5.1"):
    """Pair BUY (open) with SELL (close) rows from trade_log for given strategy."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, side, direction, entry_price, exit_price, pnl, fees, funding,
               mfe, mae, exit_reason, timestamp, strategy_version
        FROM trade_log
        WHERE strategy_version = ?
        ORDER BY id ASC
        """,
        (strategy_version,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    # Pair BUY-open rows with the next SELL-close row (same direction)
    pairs = []
    open_row = None
    for r in rows:
        is_open = r["exit_price"] is None or r["exit_price"] == 0
        if is_open:
            open_row = r
            continue
        if open_row is None:
            # SELL without a paired BUY (probably data before window starts)
            continue
        pair = {
            "open_id": open_row["id"],
            "close_id": r["id"],
            "direction": r["direction"],
            "entry_price": open_row["entry_price"],
            "exit_price": r["exit_price"],
            "entry_ts": open_row["timestamp"],
            "close_ts": r["timestamp"],
            "hold_hours": round((r["timestamp"] - open_row["timestamp"]) / 3600, 3),
            "actual_pnl_usd": r["pnl"] or 0.0,
            "actual_fees": (r["fees"] or 0.0) + (open_row["fees"] or 0.0),
            "funding": r["funding"] or 0.0,
            "mfe": r["mfe"] or 0.0,
            "mae": r["mae"] or 0.0,
            "exit_reason": r["exit_reason"],
        }
        pairs.append(pair)
        open_row = None
    return pairs


def join_events_to_trades(events, trades):
    """Match each shadow fire event to its actual close by entry_ts."""
    # Trades keyed by approximate entry_ts (unix seconds).
    # Shadow log records exact entry_ts from position["timestamp"].
    trades_by_ts = {}
    for t in trades:
        # Round to 1-second tolerance (entry_ts is float)
        key = int(t["entry_ts"])
        trades_by_ts[key] = t

    joined = []
    unmatched = []
    for e in events:
        key = int(e["entry_ts"])
        # Try exact match, then ±1s fuzz
        match = trades_by_ts.get(key) or trades_by_ts.get(key + 1) or trades_by_ts.get(key - 1)
        if match is None:
            unmatched.append(e)
            continue
        joined.append({"shadow": e, "actual": match})
    return joined, unmatched


def format_dt(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def analyze(joined):
    """Produce per-trade and aggregate stats."""
    if not joined:
        return {"count": 0, "rows": [], "summary": None}

    rows = []
    total_hypothetical = 0.0
    total_actual = 0.0
    hypothetical_wins = 0  # rule B produced a BETTER outcome than no-rule
    actual_wins_overall = 0  # actual close was positive
    for j in joined:
        s = j["shadow"]
        a = j["actual"]
        hyp = s["hypothetical_close_pnl_usd"]
        act = a["actual_pnl_usd"]
        delta = hyp - act  # positive = rule B would have saved money
        rows.append(
            {
                "entry_ts": format_dt(s["entry_ts"]),
                "close_ts": format_dt(a["close_ts"]),
                "hold_actual_h": a["hold_hours"],
                "elapsed_at_fire_h": s["elapsed_hours"],
                "direction": s["direction"],
                "entry_price": s["entry_price"],
                "price_at_fire": s["current_price"],
                "exit_price_actual": a["exit_price"],
                "mfe_at_fire": s.get("highest_pnl_pct", 0),
                "mae_actual": a["mae"],
                "hypothetical_pnl": round(hyp, 2),
                "actual_pnl": round(act, 2),
                "delta": round(delta, 2),
                "rule_B_better": delta > 0,
                "actual_exit_reason": a["exit_reason"],
            }
        )
        total_hypothetical += hyp
        total_actual += act
        if delta > 0:
            hypothetical_wins += 1
        if act > 0:
            actual_wins_overall += 1

    summary = {
        "count": len(joined),
        "total_hypothetical_pnl_usd": round(total_hypothetical, 2),
        "total_actual_pnl_usd": round(total_actual, 2),
        "net_delta_usd": round(total_hypothetical - total_actual, 2),
        "rule_B_better_trades": hypothetical_wins,
        "rule_B_worse_trades": len(joined) - hypothetical_wins,
        "actual_win_rate_in_subset": (
            round(actual_wins_overall / len(joined) * 100, 1) if joined else 0
        ),
    }
    return {"count": len(joined), "rows": rows, "summary": summary}


def print_report(events, trades, joined, unmatched, analysis, args):
    print("=" * 72)
    print("Shadow Rule B (12h compound time cap) — Analysis Report")
    print("=" * 72)
    print(f"Shadow log:    {args.log_path}")
    print(f"DB:            {args.db}")
    print(f"Strategy:      {args.strategy}")
    print(f"Report date:   {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print()
    print(f"Shadow events in log:    {len(events)}")
    print(f"Closed trades in window: {len(trades)}")
    print(f"Joined events:           {len(joined)}")
    print(f"Unmatched shadow events: {len(unmatched)} (position may still be open)")
    print()

    if analysis["count"] == 0:
        print("No joined events. Nothing to analyze yet.")
        print()
        if events and not trades:
            print("Hint: shadow events logged but no matching trades in DB.")
            print("Confirm strategy_version matches and position has actually closed.")
        return

    # Per-trade table
    print("Per-trade comparison")
    print("-" * 72)
    hdr = f'{"Entry UTC":<18} {"Hold(h)":>7} {"Actual":>8} {"Hypoth":>8} {"Δ":>8} {"Better":>7} {"Exit":<10}'
    print(hdr)
    for r in analysis["rows"]:
        better = "YES" if r["rule_B_better"] else "no"
        print(
            f'{r["entry_ts"][:18]:<18} '
            f'{r["hold_actual_h"]:>7.2f} '
            f'{r["actual_pnl"]:>+8.2f} '
            f'{r["hypothetical_pnl"]:>+8.2f} '
            f'{r["delta"]:>+8.2f} '
            f'{better:>7} '
            f'{r["actual_exit_reason"]:<10}'
        )
    print()

    # Aggregate summary
    s = analysis["summary"]
    print("Aggregate")
    print("-" * 72)
    print(f"  Trades analyzed:            {s['count']}")
    print(f"  Total actual PnL (no rule): ${s['total_actual_pnl_usd']:+.2f}")
    print(f"  Total hypothetical (rule B):${s['total_hypothetical_pnl_usd']:+.2f}")
    print(f"  Net delta (rule B − no rule):${s['net_delta_usd']:+.2f}")
    print(
        f"  Rule B better:              {s['rule_B_better_trades']} / {s['count']} trades"
    )
    print(
        f"  Rule B worse:               {s['rule_B_worse_trades']} / {s['count']} trades"
    )
    print()

    # Interpretation heuristic
    print("Interpretation")
    print("-" * 72)
    if s["net_delta_usd"] > 0 and s["rule_B_better_trades"] >= s["rule_B_worse_trades"]:
        print("  Rule B shows POSITIVE EV in the shadow window.")
        print("  Consider promoting to live once the window has >= 10 firing events.")
    elif s["net_delta_usd"] < 0:
        print("  Rule B shows NEGATIVE EV in the shadow window.")
        print("  The rule is killing positions that would have recovered.")
        print("  Consider tightening the condition or widening the time threshold.")
    else:
        print("  Inconclusive. Net delta near zero. Keep running the shadow window.")
    print()
    if s["count"] < 5:
        print(f"  WARNING: only {s['count']} data points. Not enough for a decision.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-path", default=DEFAULT_LOG)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--strategy", default="hybrid_v5.1")
    parser.add_argument(
        "--window-days", type=int, default=None,
        help="If set, only include trades that closed within this many days",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only")
    args = parser.parse_args()

    events = load_shadow_events(args.log_path)
    trades = load_closed_trades(args.db, args.strategy)

    if args.window_days:
        cutoff = datetime.now(tz=timezone.utc).timestamp() - args.window_days * 86400
        trades = [t for t in trades if t["close_ts"] >= cutoff]
        events = [e for e in events if e["fire_ts"] >= cutoff]

    joined, unmatched = join_events_to_trades(events, trades)
    analysis = analyze(joined)

    if args.json:
        print(json.dumps(
            {
                "events": len(events),
                "trades": len(trades),
                "joined": len(joined),
                "unmatched": len(unmatched),
                "analysis": analysis,
            },
            indent=2,
        ))
    else:
        print_report(events, trades, joined, unmatched, analysis, args)


if __name__ == "__main__":
    main()
