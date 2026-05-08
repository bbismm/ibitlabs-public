"""shadow-rule — Instrument-before-rule observability pattern.

Ship the log side of a decision rule before shipping the act side.
Collect evidence. Decide from data.

Usage:
    from shadow_rule import ShadowRule

    rule = ShadowRule(
        name="12h_compound_cap",
        condition=lambda state: (
            state["elapsed_hours"] > 12
            and state["pnl_pct"] < 0
            and state["highest_pnl_pct"] < 0.015
        ),
        log_path="logs/shadow_12h.jsonl",
        fire_once_per_session=True,
    )

    # On every tick:
    rule.evaluate(state={
        "elapsed_hours": 21.6,
        "pnl_pct": -0.025,
        "highest_pnl_pct": 0.0038,
        "entry_price": 88.2,
        "current_price": 85.96,
    })
    # → writes a JSONL line if condition fires, otherwise no-op.
    # → never affects the caller's execution flow.

Analysis:
    from shadow_rule import analyze

    report = analyze(
        log_path="logs/shadow_12h.jsonl",
        actual_outcomes_fn=lambda fire_event: {...},  # your domain's ground truth
    )
    print(report.summary())

See the iBitLabs reference implementation at:
    https://github.com/AgentBonnybb/ibitlabs-public/blob/main/sol_sniper_executor.py
    https://github.com/AgentBonnybb/ibitlabs-public/blob/main/scripts/analyze_shadow_12h_rule.py
"""
from shadow_rule.rule import ShadowRule, ShadowEvent, ShadowError
from shadow_rule.analyze import analyze, Report

__version__ = "0.1.0"
__all__ = ["ShadowRule", "ShadowEvent", "ShadowError", "analyze", "Report"]
