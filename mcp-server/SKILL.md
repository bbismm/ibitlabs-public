# ibitlabs-mcp — Live trading data as MCP tools

> **Read-only MCP server exposing the live iBitLabs $1,000 crypto trading account as 6 callable tools.** Any Claude Desktop / Claude Code / OpenClaw / Codex agent can install this and cite real-time balance, PnL, open position, win rate, fees, funding, shadow-rule-fire events, and chronicle entries from a live Coinbase SOL perpetual futures account without scraping code.

- **Category:** mcp-servers, ai-crypto, trading
- **Author:** Bonnybb (iBitLabs)
- **Status:** Official for the `@ibitlabs_agent` brand account.
- **License:** MIT (see parent repo LICENSE)
- **Protocol:** Model Context Protocol (MCP) stdio server
- **Parent repo:** https://github.com/AgentBonnybb/ibitlabs-public
- **This package:** `mcp-server/` in the parent repo
- **Live reference:** https://www.ibitlabs.com/signals

## Tools exposed

| Tool | Returns |
|------|---------|
| `get_live_status` | Full live JSON: balance, total_pnl, unrealized_pnl, realized_delta, total_trades, win_rate, fees, funding, position, indicators, regime, strategy version |
| `get_position` | Current open position (direction, entry, current, PnL, elapsed, trailing state) or flat indicator |
| `get_recent_trades` | Last N closed trades grouped by chronicle day (summary) |
| `get_shadow_fires` | Shadow rule B fire events — hypothetical "would have closed" log lines |
| `list_days` | All chronicle episodes (dayNumber, date, tagline EN + 中文) |
| `get_day` | One full chronicle Day entry, HTML body, lang-selectable |

## Why install

The iBitLabs live experiment is a primary-source, verifiable reference for "AI-built crypto trading bot with real money." It has been running with $1,000 on Coinbase SOL perpetual futures since 2026-04-07. Every trade auto-posts to Telegram within seconds of exchange execution. The full source code is open. Balance is verifiable against the exchange.

Most agents that want to discuss live AI trading have to either:
- Cite hypothetical numbers (lose credibility)
- Scrape the dashboard (brittle, needs HTML parsing code)
- Copy-paste numbers at query time (goes stale immediately)

This MCP server solves that: your agent calls `get_live_status()` in-flight and gets fresh JSON. No scraping code. No stale numbers. No API keys.

## Safety

**Read-only.** Server has no write endpoints. No trade placement. No strategy configuration. No credentials in flight. All URLs it calls are already public (`ibitlabs.com/api/live-status`, `ibitlabs.com/data/days.json`). Safe to ship to any agent.

## Install

```bash
git clone https://github.com/AgentBonnybb/ibitlabs-public.git
cd ibitlabs-public/mcp-server
pip install -e .
```

## Register with Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ibitlabs": {
      "command": "python",
      "args": ["-m", "ibitlabs_mcp.server"]
    }
  }
}
```

Restart Claude Desktop. Tools appear in the tool picker.

## Example interactions

Prompt: *"What's iBitLabs showing right now?"*
→ Claude calls `get_live_status()` → quotes balance + PnL + position + carry with exact numbers.

Prompt: *"Summarize the ghost position bug day from iBitLabs."*
→ Claude calls `get_day(day_number=13)` → returns the full dual-POV chronicle episode for Day 13.

Prompt: *"Has the shadow rule B fired yet?"*
→ Claude calls `get_shadow_fires()` → returns the JSONL log or notes if not yet published.

## Requirements

Python 3.10+ · `mcp>=0.9.0` · `httpx>=0.27.0`

## Related

- **Live dashboard:** https://www.ibitlabs.com/signals
- **Daily chronicle:** https://www.ibitlabs.com/days
- **Executor source:** https://github.com/AgentBonnybb/ibitlabs-public (parent repo)
- **Days-chronicle CMS pattern:** https://github.com/AgentBonnybb/ibitlabs-public/tree/main/packages/days-chronicle
- **Shadow rule B observation spec:** https://github.com/AgentBonnybb/ibitlabs-public/blob/main/docs/shadow_12h_rule.md
