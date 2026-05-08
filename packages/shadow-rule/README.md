# shadow-rule

> **Ship the instrument, not the rule.** A tiny Python library for the instrument-before-rule observability pattern: evaluate a proposed decision rule every tick, log when it would have fired, **never execute**. After 30 days of evidence, decide whether the rule is worth shipping for real.

Extracted from the iBitLabs live trading experiment, where a proposed 12-hour compound exit rule was shipped as a shadow-mode instrument rather than a live execution change. On first tick after restart, the log wrote one line. Thirty days of lines become a dataset. The dataset decides.

## The pattern

Most teams ship a proposed rule by debating it, merging it, and watching for the first time it fires badly. That debate is unfalsifiable — if the rule hasn't fired yet, "the condition hasn't been wrong YET" feels like the same thing as "the condition is right." And once it's live, rolling it back costs face.

The shadow-rule pattern separates the **write side** from the **act side** of a decision rule:

1. **Write side:** when the condition fires, append a JSONL line saying "here is what I would have done."
2. **Act side:** nothing. The system keeps running exactly as before. The caller's control flow is untouched.

After N days, a small analyzer joins each fire event to the eventual real outcome (provided by your domain — the actual trade close, the actual test disposition, the actual conversion) and computes net EV delta.

The rule earns its promotion — or it doesn't. Either way you know from data, not from the rhetorical intensity of the original proposal.

## Where this comes from

iBitLabs had a Moltbook scan recommending a 12-hour position-time-cap rule as URGENT. The operator (Bonnybb) rejected it on principle — but hadn't backtested. When asked "did you actually test it," the honest answer was no.

Instead of litigating "ship vs don't ship," a **compound** version of the rule (a shape the operator hadn't evaluated) was shipped as ~30 lines of shadow instrumentation in the live trading executor. First tick after restart, the log wrote one row. 30 days from now, the EV analyzer decides.

Reference implementation is in the parent repo:
- https://github.com/AgentBonnybb/ibitlabs-public/blob/main/sol_sniper_executor.py (the `_log_shadow_12h_rule` method)
- https://github.com/AgentBonnybb/ibitlabs-public/blob/main/scripts/analyze_shadow_12h_rule.py (domain-specific analyzer)
- https://github.com/AgentBonnybb/ibitlabs-public/blob/main/docs/shadow_12h_rule.md (full spec + decision criteria)

**This package is the generalized, trading-domain-agnostic version of that pattern.** Use it for:

- **Trading / risk systems** — shadow proposed exit rules, stop-loss rules, position-sizing rules
- **Auth / trust-and-safety** — shadow a stricter flag-rule and see the true-positive rate before enforcing
- **A/B onboarding flows** — shadow a "show the tooltip" condition and see how often it would have fired
- **Alerting / monitoring** — shadow a paging rule for 30 days to tune it before it pages anyone at 3am
- **Autonomous agents** — shadow a "stop and ask the human" condition to learn what fraction of decisions would escalate

## Invariants

1. **Never mutates caller state.** The rule reads only. The only observable output is a JSONL log line.
2. **Swallows its own errors.** A broken shadow rule must NEVER break the caller. All exceptions in the fire path are caught, logged to `logging`, and the caller continues.
3. **Fire-once by default.** Each session (trade, user flow, deployment window) fires at most one event. The flag persists so bot restarts don't double-count. Set `fire_once_per_session=False` to log every tick.
4. **Deterministic JSONL format.** One event per line, stable schema, versioned.

## Install

```bash
pip install shadow-rule     # once published to PyPI
# — or from source —
git clone https://github.com/AgentBonnybb/ibitlabs-public.git
cd ibitlabs-public/packages/shadow-rule
pip install -e .
```

## Minimum viable usage

```python
from shadow_rule import ShadowRule, analyze

# 1. Define the condition as a pure function of state.
def compound_rule(state):
    return (
        state["elapsed_hours"] > 12
        and state["pnl_pct"] < 0
        and state["highest_pnl_pct"] < 0.015
    )

rule = ShadowRule(
    name="12h_compound_cap",
    condition=compound_rule,
    log_path="logs/shadow_12h.jsonl",
    fire_once_per_session=True,
)

# 2. In your tick loop, call evaluate() with current state.
rule.evaluate({
    "elapsed_hours": 21.6,
    "pnl_pct": -0.025,
    "highest_pnl_pct": 0.0038,
    "entry_price": 88.2,
    "current_price": 85.96,
})
# → appends a JSONL line if the condition fires.
# → returns True/False (for observability only — ignore it; caller flow unchanged).
# → never raises.

# 3. When session concludes (trade closes, user flow ends), reset:
rule.reset_session()

# 4. After 30 days, analyze:
def actual_outcome(fire_event):
    # Look up the actual outcome by session_id or fire_ts or state['entry_ts']
    # Return a dict with the fields ev_fields expects, or None to skip.
    return {
        "actual_pnl": -12.20,
        "hypothetical_pnl": -11.22,
    }

report = analyze(
    log_path="logs/shadow_12h.jsonl",
    actual_outcomes_fn=actual_outcome,
)
print(report.summary())
# Shadow rule analysis (N fires, P paired, U unpaired)
#   paired_count: P
#   rule_better_count: ...
#   total_delta: +$42.30
#   mean_delta: +$1.41
#   ...
```

## Persistence across restarts

`ShadowRule` keeps an in-memory flag to implement fire-once. If your system restarts mid-session, that flag is lost by default — and the rule will fire again on the first post-restart tick, double-counting.

Two options:

```python
# Option A — the rule's own snapshot API
snap = rule.snapshot_flag()      # {"fired_in_session": True, "session_id": "abc"}
# persist `snap` in your system's state
# ...on restart...
rule.restore_flag(snap)

# Option B — use fire_once_per_session=False and dedupe downstream
# in your analyzer. Simpler but produces duplicate log lines.
```

The iBitLabs reference implementation uses Option A — see `sol_sniper_executor.py` for the `_save_state` / `_load_state` pattern where the shadow flag is persisted alongside other position state.

## What this is NOT

- **Not an A/B testing framework.** This is one-rule observation; for multi-arm experiments use dedicated tooling.
- **Not a feature flag system.** No runtime toggles, no segmentation. A rule is on or off at deploy time.
- **Not a time-series DB.** JSONL log scales to thousands of events, not millions. Beyond that, ship to a real log pipeline.

## License

MIT.

## Maintainer

Bonnybb · https://github.com/AgentBonnybb · Issues welcome in the parent repo.
