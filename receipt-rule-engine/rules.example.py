"""Example rules for the Receipt rule engine.

Copy this file to `rules.py` and edit. The engine reads `rules.py` (NOT
`rules.example.py`) on startup. `rules.py` is gitignored so your local
config doesn't pollute the fork.

After editing, reload the daemon. If you're running it under launchd:

    launchctl kickstart -k gui/$(id -u)/com.YOURORG.receipt-rule-engine

Or just kill its PID — launchd respawns within ~30s and picks up the
new rules.
"""

import os

HOME = os.path.expanduser("~")

# Map short chain names → JSONL paths. The engine watches all of these.
# Edit to point at your own receipt chains.
CHAINS = {
    "shadow": f"{HOME}/receipts/sniper-shadow.realtime.receipt.jsonl",
    "live":   f"{HOME}/receipts/sniper-live.realtime.receipt.jsonl",
}

# Receipt rule schema:
#   name:               required, debounce key
#   chains:             optional, default ["*"] — list of chain names or "*"
#   match:              required, dict of {field_path: expected}
#       field_path uses dotted notation: "data.action", "agent", etc.
#       expected: scalar (equality), list (membership), or bool (truthiness)
#   do:                 required, list of action dicts
#   debounce_seconds:   optional, default 0 — same rule won't fire twice within N seconds
#
# Tier discipline (operator policy, not enforced by code):
#   Tier 1 (idempotent, reversible) → safe to `auto: true`: anchor, reconcile, sync
#   Tier 2 (state-fixing, reversible w/ effort) → auto + circuit breaker
#   Tier 3 (irreversible, live money) → ntfy only, NEVER set `auto: true`
#     Examples: kill positions, bootout the trading bot, modify chains
RULES = [
    # Example: ntfy push on any reconciliation FAIL event from any chain.
    {
        "name": "reconcile-fail-push",
        "match": {"data.kind": "reconcile", "data.status": "fail"},
        "do": [
            {"type": "ntfy", "topic": "YOUR_NTFY_TOPIC", "priority": 4,
             "title": "Reconciliation failed", "message": "Chain {chain} reported reconcile fail at {ts}"},
        ],
        "debounce_seconds": 300,
    },

    # Example: ABSENT pattern — fire if no heartbeat in 10 minutes.
    # Useful for detecting a stuck or crashed bot. The engine polls this
    # rule even when no events arrive; `absent_for_seconds` triggers a
    # synthetic event.
    {
        "name": "heartbeat-stale",
        "chains": ["live"],
        "match": {"data.kind": "heartbeat", "absent_for_seconds": 600},
        "do": [
            {"type": "ntfy", "topic": "YOUR_NTFY_TOPIC", "priority": 5,
             "title": "Live chain silent ≥10min", "message": "No heartbeat on `live` since {last_event_ts}"},
        ],
        "debounce_seconds": 600,
    },

    # Example: Tier-1 auto action — anchor the chain to an external store
    # nightly. `auto: true` opts this rule's shell action in to execution.
    # Without `auto: true`, the engine logs "BLOCKED" and skips.
    # {
    #     "name": "anchor-daily-04utc",
    #     "match": {"data.kind": "heartbeat", "hour_utc": 4},
    #     "do": [
    #         {"type": "shell", "auto": True,
    #          "cmd": f"{HOME}/receipt-rule-engine/scripts/anchor_daily.py"},
    #     ],
    #     "debounce_seconds": 23 * 3600,
    # },
]
