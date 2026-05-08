"""shadow_rule.analyze — post-hoc EV analysis of a shadow log.

Join each fire event to the eventual actual outcome (provided by the
caller) and compute summary metrics: count, win/loss breakdown, net EV
delta, per-event rows.

The caller's `actual_outcomes_fn` is a function (fire_event -> dict) that
returns the ground truth for that session — e.g. for trading: the actual
close PnL; for auth testing: the real disposition (true-positive, false-
positive); for a UX experiment: the conversion outcome.

Returns a structured `Report` with `summary()`, `to_json()`, and raw rows.
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable


@dataclass
class Report:
    total_fires: int
    paired: int
    unpaired: int
    summary_stats: dict
    rows: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        s = self.summary_stats
        lines = [
            f"Shadow rule analysis ({self.total_fires} fires, {self.paired} paired, "
            f"{self.unpaired} unpaired)",
        ]
        for k, v in s.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent, default=str)


def _load_events(log_path: Path) -> list[dict]:
    out = []
    if not log_path.exists():
        return out
    with log_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def analyze(
    log_path: str,
    actual_outcomes_fn: Callable[[dict], dict | None],
    *,
    ev_fields: tuple[str, ...] = ("actual_pnl", "hypothetical_pnl"),
) -> Report:
    """Join fire events to actual outcomes and compute summary EV metrics.

    Args:
        log_path: Path to JSONL shadow log written by ShadowRule.
        actual_outcomes_fn: Given a fire event dict, return a dict with the
            eventual actual outcome. Minimum keys: the two mentioned in
            `ev_fields` (default: "actual_pnl" and "hypothetical_pnl").
            Return None to mark an event as unpaired (outcome not yet known).
        ev_fields: Tuple of (actual_field, hypothetical_field). Delta is
            computed as hypothetical - actual (positive = rule-B-was-better).

    Returns:
        Report with count, paired/unpaired, summary stats, and per-row data.
    """
    events = _load_events(Path(log_path))
    rows = []
    deltas = []
    unpaired = 0
    actual_key, hypothetical_key = ev_fields

    for e in events:
        outcome = actual_outcomes_fn(e)
        if outcome is None:
            unpaired += 1
            continue
        try:
            actual = float(outcome[actual_key])
            hypothetical = float(outcome[hypothetical_key])
        except (KeyError, TypeError, ValueError):
            unpaired += 1
            continue
        delta = hypothetical - actual
        deltas.append(delta)
        rows.append({
            "fire_iso": e.get("fire_iso"),
            "session_id": e.get("session_id"),
            "rule_name": e.get("rule_name"),
            actual_key: round(actual, 4),
            hypothetical_key: round(hypothetical, 4),
            "delta": round(delta, 4),
            "rule_better": delta > 0,
            "state": e.get("state", {}),
        })

    summary_stats = {
        "paired_count": len(deltas),
        "rule_better_count": sum(1 for d in deltas if d > 0),
        "rule_worse_count": sum(1 for d in deltas if d < 0),
        "rule_neutral_count": sum(1 for d in deltas if d == 0),
    }
    if deltas:
        summary_stats.update({
            "total_delta": round(sum(deltas), 4),
            "mean_delta": round(statistics.fmean(deltas), 4),
            "median_delta": round(statistics.median(deltas), 4),
            "stdev_delta": (round(statistics.stdev(deltas), 4)
                            if len(deltas) > 1 else 0.0),
            "min_delta": round(min(deltas), 4),
            "max_delta": round(max(deltas), 4),
        })

    return Report(
        total_fires=len(events),
        paired=len(deltas),
        unpaired=unpaired,
        summary_stats=summary_stats,
        rows=rows,
    )
