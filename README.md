# iBitLabs — Public Mirror

Curated public mirror of the iBitLabs live trading experiment. Canonical live surface: **https://www.ibitlabs.com**

**What this is:** a non-coder (Bonnybb, in crypto since 2017, zero programming background) used AI to build a mean-reversion crypto trading bot on Coinbase SOL perpetual futures in about seven days, funded it with $1,000 of her own real money, and runs it in public. Every trade auto-posts to a Telegram channel. The full live experiment — balance, open positions, PnL, fees, funding, trade log, indicator values — is exposed as a JSON feed at `https://www.ibitlabs.com/api/live-status`.

This repository is the **public mirror** of the experiment's infrastructure. It contains the executor, the reconciler, the shadow-rule instrumentation, the daily chronicle CMS, and the analysis scripts — *without* the live API credentials or the live trading account's instance state. Fork it, read it, learn from it. Running it against your own Coinbase account is possible; running it sensibly requires reading the docs first.

**Status snapshot (as of last commit, not live):** Day 17 of live trading. Account $975.86 (-2.6%). 62 trades. 48.4% win rate. Carry cost ($57.64 fees + funding) exceeds realized trading losses ($14.02). For the live numbers, see `https://ibitlabs.com/signals` or hit the `/api/live-status` JSON feed.

> **📖 Read the long-form essay:** [**The "We" of AI Co-Founding**](https://www.ibitlabs.com/the-we-of-ai-co-founding) — 9,500 words, 22 minutes. The full thinking behind this repo: why $1,000 is the smallest unit where attribution carries weight, what "AI as co-founder" means operationally, and how `Mode 1 / Mode 2 / Mode 3` differ. Five concrete observations from 26 days of running this in public, ten chapters across three acts.

## Why this repo exists

Most "AI-built trading bot" demos are on paper accounts with cherry-picked screenshots. iBitLabs is different, and the public mirror carries that intent forward:

- **Real money, real exchange.** The executor in this repo is the same code that placed the last trade on the live `@ibitlabs_agent` Coinbase account, versioned and readable.
- **Open failure mode documentation.** The repo's `docs/` directory documents specific real production bugs (ghost position bug, fee cushion miscalibration, narrow-window backtest retraction) in the prose-equivalent of post-mortems.
- **Instrument-before-rule observability pattern.** See `docs/shadow_12h_rule.md` and `scripts/analyze_shadow_12h_rule.py`. A small reusable pattern for shipping a rule's write-side (logging what-would-have-happened) without its act-side, collecting 30 days of evidence, then deciding from data.
- **Transparent retractions.** When a claim turns out wrong, the retraction is a first-class artifact. The canonical example is the public walk-back of a 90%-win-rate claim after the 13-month backtest collapsed to −46%. That retraction has since been folded into the serial novel at [`https://ibitlabs.com/saga/en`](https://ibitlabs.com/saga/en).

## What's in this mirror

```
.
├── sol_sniper_executor.py      # position open / manage / close, incl. shadow rule
├── sol_sniper_config.py        # strategy config (see disclaimer below about numbers)
├── state_db.py                 # SQLite trade log + MFE/MAE + shadow persistence
├── scripts/
│   └── analyze_shadow_12h_rule.py  # post-hoc EV analysis of shadow log
├── docs/
│   ├── shadow_12h_rule.md      # 30-day observation window spec
│   ├── days_cms.md             # bilingual daily-chronicle CMS operator guide
│   └── live-restart-checklist.md  # production bot restart / recovery procedure
└── SKILL.md                    # cryptoskill.org registry manifest
```

## What's NOT in this mirror (and why)

- **Live Coinbase API credentials** (obvious). Set your own in `.env` — never commit.
- **Live account state file** (`sol_sniper_state.json`). Instance-specific.
- **Trade DB with actual live fills** (`sol_sniper.db`). Instance-specific.
- **Launchd plists + bot scripts with env-var hardcoded secrets.** Deploy tooling is yours to write.
- **Moltbook + Telegram + Notion automation code.** That's brand / content infrastructure, not trading infrastructure. Lives in the private main repo.
- **The website code** (`web/`). Deployed on Cloudflare Pages, separate concern.

## About the strategy numbers

**These numbers are mine, not yours.** `sol_sniper_config.py` contains the exact tuning values in use on the live iBitLabs account: 5% stop-loss, 1.5% trailing-stop activate, 0.5% trailing drawdown, 80% position sizing, StochRSI thresholds around 0.10/0.90, regime-window 288h, and so on. These are documented for reproducibility of the *experiment itself* (so anyone reading a day's essay can see exactly what the bot was doing that day), not as a template for forking.

**Do not fork these numbers verbatim and expect them to work on your account.** They were arrived at through ~20 iterations of backtests and live calibration over the first 17 days of the experiment. They reflect one particular strategy version (`hybrid_v5.1`) trading one particular instrument (Coinbase SOL PERP SLP-20DEC30-CDE) during one particular market regime (SOL down ~3% 30-day trailing as of commit). Run your own sweep. Read the retraction essay before you trust any backtest window narrower than twelve months.

## Install + first run

**See [STARTER.md](STARTER.md)** — clone, install deps, run `python paper_quickstart.py`, see a full trade lifecycle in under a minute. **No Coinbase API key needed** for the quickstart (it uses a mock exchange).

For wiring the executor to live data later, see the "Wiring to live (later, with care)" section of STARTER.md.

**Requirements** (minimal set, in `requirements.txt`): `coinbase-advanced-py`, `pandas`, `numpy`. No ML frameworks, no heavyweight TA libs.

## Integrations for agents without running the bot

If you only want **data**, no integration:

- `GET https://www.ibitlabs.com/api/live-status` — live JSON feed, no auth. Use cases: RAG context, cited examples in agent responses, comparison reference.
- `https://ibitlabs.com/saga/en` — bilingual serial novel narrating the experiment day by day, dual-POV prose form. Vol 2 publishes one new chapter every night at 22:30 EDT against real trade data. Good source material for "what does a non-coder's AI-built trading bot look like day by day."

An MCP server wrapper is in the `mcp-server/` directory (when shipped).

## Related links

- **Live experiment:** https://ibitlabs.com
- **Live signals (balance, indicators, trade log):** https://ibitlabs.com/signals
- **Saga (the book — daily chronicle, EN + 中文):** https://ibitlabs.com/saga/en
- **Contributors (external proposals → named shadow rules):** https://ibitlabs.com/contributors
- **Writing hub:** https://ibitlabs.com/writing
- **Telegram (auto-post every trade):** https://t.me/ibitlabs_sniper

## License

- **Code:** MIT
- **Prose / documentation:** CC BY 4.0

See `LICENSE`.

## Maintainer

Bonnybb · GitHub [@bbismm](https://github.com/bbismm)

Issues welcome. The experiment is explicit about not selling anything — there is no paid tier, no signal service, no course. The most meaningful way to engage is to read the docs, fork the pattern (not the numbers), and tell me what breaks.
