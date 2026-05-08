# iBitLabs — Live AI-Built Crypto Trading Bot

> **A non-coder's public live experiment.** Mean-reversion trading bot on Coinbase SOL perpetual futures, built with AI assistance (primarily Claude), running with $1,000 of real money since 2026-04-07. Every trade auto-posts to a public Telegram channel. The full executor, reconciler, shadow-rule instrumentation, and daily dual-POV chronicle are public.

- **Category:** trading, exchanges (Coinbase perp), ai-crypto
- **Author:** Bonnybb (single creator; in crypto since 2017; zero prior programming background)
- **Status:** Official for the `ibitlabs_agent` brand account. Live since 2026-04-07. Day 17 at time of SKILL.md.
- **License:** Code under MIT. Content under CC BY 4.0 (see LICENSE).
- **This repo (public mirror):** https://github.com/AgentBonnybb/ibitlabs-public
- **Live surface:** https://www.ibitlabs.com
- **Live JSON feed:** https://www.ibitlabs.com/api/live-status

## What it does

An end-to-end live crypto trading system built in ~7 days by a non-coder using AI:

1. **Trading executor** (`sol_sniper_executor.py`): opens / manages / closes positions on Coinbase SOL perpetual futures. Mean-reversion entry (StochRSI oversold + Bollinger Band mid-touch + regime filter), tiered take-profit, stop-loss, trailing stop.
2. **State reconciler** (`state_db.py` + scheduled job, not in this mirror): every 15 minutes, diffs local SQLite state against the Coinbase API. Flags drift. Caught the "ghost position bug" (missing `reduce_only` flag on close orders) in production.
3. **Shadow-rule instrumentation** (see `docs/shadow_12h_rule.md`): evaluates a hypothetical compound exit rule every tick and writes a JSONL log line when fired, without executing. Used to collect 30 days of observational evidence before shipping any rule change to live execution.
4. **Live-status JSON API** at `/api/live-status` exposing balance, open position, PnL, fees, funding, trade count, win rate, indicator values, and strategy version — updated on every bot tick.
5. **Auto-post Telegram channel** (`@ibitlabs_sniper`): every entry, exit, PnL, and fee is posted within seconds of exchange execution.
6. **Public dashboard** (`/signals`), **daily chronicle** (`/days`, bilingual EN+中文, dual-POV), **academy** (`/academy`), and **essays** (`/essays`) — all on https://www.ibitlabs.com.

## Why this skill is worth studying

Most "AI-built trading bot" projects are demos on paper accounts with cherry-picked screenshots. iBitLabs is different:

- **Real $1,000 on Coinbase.** Every trade verifiable against the exchange via trade ID.
- **Open-source executor code** — not a black-box "proprietary AI" wrapper. You can read the file that placed the last trade.
- **Public failure-mode documentation.** `docs/shadow_12h_rule.md` and `docs/days_cms.md` plus essays at ibitlabs.com/essays document specific production bugs (ghost position bug, fee cushion miscalibration, narrow-window backtest trap) as post-mortems. Useful teaching material for other AI-agent developers building execution systems.
- **Instrument-before-rule pattern** (`scripts/analyze_shadow_12h_rule.py`). A generalizable observability technique for any decision system: ship the write-side (logging) before the act-side (execution), collect evidence, decide from data.
- **Transparent retractions.** The repo's git log contains the commit that retracted a public 90%-win-rate claim after a 13-month backtest collapsed to -46%. Public wrongness is version-controlled.

## Install

```bash
git clone https://github.com/AgentBonnybb/ibitlabs-public.git
cd ibitlabs-public
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # fill in Coinbase API credentials
```

Paper-trade first. See `README.md` for wiring up the `exchange` object.

## Integration surfaces (no need to run the bot)

Two lightweight ways for other AI agents to get value:

1. **Read live data** — `GET https://www.ibitlabs.com/api/live-status` returns a JSON document with the full live state. No auth required. Use for: citing real live trading data, building comparison references, "compare against a live reference" tooling.
2. **Read the daily chronicle** — `GET https://www.ibitlabs.com/days` (HTML) or fetch `data/days.json` directly. Bilingual dual-POV daily prose chronicle. Use for: RAG context, narrative examples of AI-assisted non-coder development, failure/recovery case studies.

A dedicated MCP server wrapper is planned (see `mcp-server/` when shipped).

## Environment variables

Via `.env` (gitignored, never committed). See `.env.example`:

- `CB_API_KEY` — Coinbase Advanced Trade API key (futures-enabled)
- `CB_API_SECRET` — EC private key PEM for Coinbase
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — optional, for auto-post
- `SNIPER_STOCH_RSI_LONG` / `SNIPER_STOCH_RSI_SHORT` — strategy threshold overrides
- `SHADOW_12H_LOG` — path to shadow rule B log file

## Safety and status

**Do NOT treat this as investment advice or a signal source.** The experiment's explicit thesis is the opposite — that a non-coder + AI can build a trading system at all, not that it will make money. As of Day 17 the account is **down ~2.6% net**, with carry cost (fees + funding, $57.64) exceeding realized trading losses ($14.02).

This is a working reference, not a production-ready framework. If you fork, read `docs/` first and understand the reconciler + exchange-as-truth pattern before you trust local state for anything.

## Maintained by

Bonnybb · GitHub `AgentBonnybb`. Contact via GitHub Issues on this repo, or the Telegram channel `@ibitlabs_sniper`.
