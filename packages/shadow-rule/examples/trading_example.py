"""Example: shadow a compound 12-hour time-cap rule on a trading bot.

Shows the ship-the-instrument-not-the-rule pattern.
"""
from shadow_rule import ShadowRule, analyze


# 1. Define the rule as a pure condition.
def compound_12h_rule(state: dict) -> bool:
    """Fire when: elapsed>12h AND currently red AND trailing never armed."""
    return (
        state.get("elapsed_hours", 0) > 12
        and state.get("pnl_pct", 0) < 0
        and state.get("highest_pnl_pct", 0) < 0.015
    )


rule = ShadowRule(
    name="12h_compound_cap_v1",
    condition=compound_12h_rule,
    log_path="logs/shadow_12h_cap.jsonl",
    fire_once_per_session=True,   # at most one event per position
)


# 2. In the bot's tick loop, call evaluate() with the current state.
#    This would be inside your existing check_position() method.
def on_each_tick(position, current_price):
    state = {
        "elapsed_hours": (position.now() - position.opened_at) / 3600,
        "pnl_pct": (current_price - position.entry_price) / position.entry_price,
        "highest_pnl_pct": position.highest_pnl_pct,
        "entry_price": position.entry_price,
        "current_price": current_price,
        "direction": position.direction,
    }
    # The rule writes a JSONL line if it fires. Always returns immediately.
    # Your caller code flow is unaffected.
    rule.evaluate(state)


# 3. When a position closes, reset the session so the rule can fire again
#    on the next position.
def on_position_close():
    rule.reset_session()


# 4. After 30 days of data, analyze.
def monthly_review():
    # Your actual_outcomes_fn returns the real close PnL for the session
    # that fired. Match by session_id or entry_ts, whatever your DB has.
    def actual_outcome(fire_event: dict):
        session_id = fire_event["session_id"]
        # ... look up the actual trade close by session_id ...
        return {
            "actual_pnl": -12.20,       # what the trade actually closed at
            "hypothetical_pnl": -11.22,  # what the rule would have locked in
        }

    report = analyze(
        log_path="logs/shadow_12h_cap.jsonl",
        actual_outcomes_fn=actual_outcome,
    )
    print(report.summary())
    # Decide: promote rule to live, reject, or extend the window.
