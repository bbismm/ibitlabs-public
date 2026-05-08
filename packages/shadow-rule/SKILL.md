# shadow-rule — Instrument-before-rule observability pattern

> **A tiny Python library for shipping the log-side of a proposed decision rule before the act-side.** Evaluate a rule every tick, write a JSONL line when it would have fired, never execute. After 30 days of evidence, decide whether to promote it. Extracted from the iBitLabs live crypto trading experiment where a proposed 12-hour compound exit rule was shipped as shadow-mode instrumentation rather than live execution — collecting evidence before committing.

- **Category:** dev-tools, ai-crypto (useful for agentic decision systems beyond trading)
- **Author:** Bonnybb (iBitLabs)
- **Status:** Community. Extracted 2026-04-23 from the iBitLabs trading executor.
- **License:** MIT
- **Parent repo:** https://github.com/AgentBonnybb/ibitlabs-public
- **This package:** `packages/shadow-rule/`
- **Reference implementation:** `sol_sniper_executor.py` (the `_log_shadow_12h_rule` method) and `docs/shadow_12h_rule.md`

## What it is

A 200-line Python library implementing the instrument-before-rule pattern:

- `ShadowRule(name, condition, log_path)` — evaluate a condition each tick, append a JSONL line on fire
- `analyze(log_path, actual_outcomes_fn)` — join fire events to actual outcomes, compute net EV delta

Zero runtime dependencies. Pure stdlib + dataclasses.

## Why it exists

Most teams ship a proposed rule by debating it, merging it, and waiting for the first time it fires badly. That debate is unfalsifiable before deploy. Once deployed, rollback costs face.

The shadow pattern separates:

- **Write side:** when the condition fires, log a JSONL line.
- **Act side:** nothing. The system keeps running exactly as before.

After N days, an analyzer joins fire events to actual outcomes (your domain's ground truth) and computes net EV delta. The rule earns its promotion from data, not rhetoric.

## Generalizes beyond trading

Reference implementation is trading. Same pattern works for:

- **Trading / risk systems:** shadow proposed exits, stops, position sizing
- **Auth / trust-and-safety:** shadow a stricter flag before enforcement
- **Onboarding A/B:** shadow a "show tooltip" condition to learn true-positive rate
- **Alerting / paging:** shadow a page condition for 30 days before anyone gets paged at 3am
- **Agent decision rules:** shadow a "stop and ask human" condition to learn escalation rate

## Invariants (the safety contract)

1. **Never mutates caller state.** Reads only. The only observable output is a log file write.
2. **Swallows all its own errors.** A broken rule cannot break the caller. Ever.
3. **Fire-once per session by default.** Each observational session fires at most once. Persistence snapshot API for state-surviving restarts.
4. **Deterministic JSONL format.** Versioned schema. One event per line.

## Install

```bash
git clone https://github.com/AgentBonnybb/ibitlabs-public.git
cd ibitlabs-public/packages/shadow-rule
pip install -e .
```

## Minimum example

```python
from shadow_rule import ShadowRule

rule = ShadowRule(
    name="12h_compound_cap",
    condition=lambda s: (
        s["elapsed_hours"] > 12
        and s["pnl_pct"] < 0
        and s["highest_pnl_pct"] < 0.015
    ),
    log_path="logs/shadow_12h.jsonl",
    fire_once_per_session=True,
)

# In your tick loop:
rule.evaluate({
    "elapsed_hours": 21.6,
    "pnl_pct": -0.025,
    "highest_pnl_pct": 0.0038,
})
# → writes a JSONL line if all three conditions true. Returns boolean.
# → never raises, never mutates state.

# When the session ends (trade closes, user flow completes):
rule.reset_session()

# After N days, analyze:
from shadow_rule import analyze
report = analyze("logs/shadow_12h.jsonl", actual_outcomes_fn=my_outcome_fn)
print(report.summary())
```

See `examples/trading_example.py` for the full trading-domain example.

## Related

- **Full design doc:** https://github.com/AgentBonnybb/ibitlabs-public/blob/main/docs/shadow_12h_rule.md
- **Reference implementation in production:** https://github.com/AgentBonnybb/ibitlabs-public/blob/main/sol_sniper_executor.py
- **Domain-specific analyzer (trading):** https://github.com/AgentBonnybb/ibitlabs-public/blob/main/scripts/analyze_shadow_12h_rule.py
- **Live trading data the reference shadowed:** https://www.ibitlabs.com/api/live-status
- **30-day review of the reference rule** will happen 2026-05-23; the decision will be logged as an addendum to the design doc above.

## Requirements

Python 3.10+. No external dependencies.

## License

MIT. Attribution for pattern: "shadow-rule pattern · iBitLabs" with a link to this package.

## Maintainer

Bonnybb · GitHub `AgentBonnybb`. Issues welcome in the parent repo.
