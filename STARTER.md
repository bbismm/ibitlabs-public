# STARTER — Run iBitLabs paper bot in 1 hour

You have $1,000 and curiosity. This guide gets you from `git clone` to "I just watched a paper bot run a full trade lifecycle" in under an hour. **No live money. No Coinbase API key needed for this kit.** We assume you've installed Python before; nothing else.

## What you'll see at the end

- The same `SniperExecutor` class running live on the iBitLabs $1,000 account opens a paper position, runs trailing logic on price ticks, fires a trailing stop, closes the position
- A SQLite database with the full trade row: direction, entry price, exit price, fees, exit reason, regime
- A state file mirroring what the live bot writes for crash recovery
- A next-steps menu: keep observing paper, read live signals, propose a contributor rule, or read the strategy docs

## What this does NOT give you

- **A signal generator.** `sol_sniper_signals.py` is gitignored on purpose — it's the strategy's core. The quickstart hand-crafts a mock signal so you can see the executor lifecycle without us shipping the signal logic.
- **A profitable bot.** This is an executor demo, not a strategy template. README.md explains why "fork the pattern, not the numbers."
- **Live wiring.** That needs `docs/live-restart-checklist.md` and reading the production failure-mode docs first. We gate it deliberately.

## Prerequisites

- macOS or Linux (Windows works but we don't test it)
- Python 3.10+
- 30 min if everything works, 1 hr if it's your first venv

(No Coinbase API key needed. The quickstart uses a mock exchange — no network calls. Coinbase keys come in *later*, when you decide to wire the executor to live data.)

## Step 1 — Clone and install (5 min)

```bash
git clone https://github.com/bbismm/ibitlabs-public.git
cd ibitlabs-public
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Step 2 — Run the quickstart (1 min)

```bash
python paper_quickstart.py
```

Expected output:

```
[QUICKSTART] Loaded config: hybrid_v5.1, capital=$1000.0
[QUICKSTART] Feeding mock LONG signal at $100.00
[SNIPER OPEN] LONG SLP-20DEC30-CDE | Amount: $800.00 | Qty: 1 | Price: ~100.00
[SNIPER FILLED] LONG SLP-20DEC30-CDE @ 100.00 x 1 | Amount: $800.00 | ID: mock-1
[QUICKSTART] Tick 1: price=$100.00 — hold
[SNIPER TRAILING] Activated! Unrealized +2.00%
[QUICKSTART] Tick 2: price=$102.00 — hold [TRAILING ARMED]
[QUICKSTART] Tick 3: price=$101.00 — action=close_trailing
[SNIPER CLOSE] Close LONG SLP-20DEC30-CDE @ 101.00 | Gross: $+5.00 | Fee: -$0.50 | Net: +$4.50 (+1.00%) | Trailing stop | Peak +2.00% -> Drawdown 1.00% | Locked +1.00% ($+5.00)
[QUICKSTART] Closed. PnL: $+4.50
[QUICKSTART] Done.
```

Then inspect the trade row:

```bash
sqlite3 paper_quickstart.db 'SELECT direction, entry_price, exit_price, fees, pnl, exit_reason FROM trade_log;'
```

## Step 3 — Where to go from here (pick one)

- **Keep tinkering** — change the `price_path` or `signal` in `paper_quickstart.py` to see how the executor reacts to different scenarios (TP hit, SL hit, peak-fade-to-breakeven, etc.)
- **Look at live data** — `curl https://www.ibitlabs.com/api/live-status | jq` returns the live $1,000 account state. No auth.
- **Read the strategy** — `sol_sniper_config.py` shows every tunable (StochRSI thresholds, trailing %, regime window). `docs/shadow_12h_rule.md` shows how we observe a rule for 30 days before shipping it.
- **Propose to contributors** — see [CONTRIBUTING.md on the main repo](https://github.com/bbismm/ibitlabs/blob/main/CONTRIBUTING.md). One observed rule that survives 30 days of shadow data earns permanent credit.

## What's NOT in this mirror (and why)

| File | Why excluded |
|---|---|
| `sol_sniper_signals.py` | Strategy core — gitignored on the live repo too |
| `sol_sniper_main.py` | Live runtime entry — requires deployment infra |
| Live launchd plists | Operator-specific; write your own |
| Moltbook / Telegram automation | Brand layer, not trading |

## Wiring to live (later, with care)

When you're ready to point this at real money:

1. Create a Coinbase Advanced Trade API key (View + Trade, **NOT** Transfer). See `.env.example`.
2. Write your own exchange wrapper that satisfies the methods the mock implements: `fetch_ticker`, `fetch_positions`, `fetch_balance`, `create_limit_order`, `close_perp_position`, `get_order_fill_price`, `cancel_orders`.
3. Read `docs/live-restart-checklist.md` and the `docs/shadow_*` series before you ship a single live trade.
4. The live bot took 17+ days to harden against the ghost-position bug, the close_position SDK 404, the Coinbase IP allowlist edge case. Skipping that on real money is how you find new bugs the expensive way.
