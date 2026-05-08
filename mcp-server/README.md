# ibitlabs-mcp

> **MCP server exposing the live iBitLabs crypto-trading experiment as callable tools.** Any MCP-compatible agent (Claude Desktop, Claude Code, OpenClaw, Codex) can install this and get real-time balance / PnL / position / win rate / open-trade context from a live $1,000 trading account. No API keys required; no write operations possible.

## What it gives you

Six read-only tools:

| Tool | Returns |
|------|---------|
| `get_live_status` | Full live JSON: balance, PnL, open position, fees, funding, trades, WR, indicator values, regime |
| `get_position` | Just the current open position (or flat indicator) |
| `get_recent_trades` | Last N closed trades, grouped by day, with entry/exit/PnL |
| `get_shadow_fires` | Shadow rule B log entries — hypothetical "would have closed" events |
| `list_days` | Summary of all chronicle episodes (dayNumber, date, tagline) |
| `get_day` | One specific Day entry, full body, EN or 中文 |

All tools hit the public `/api/live-status` endpoint at `ibitlabs.com` and the chronicle JSON at `ibitlabs.com/data/days.json`. **No auth. No writes. No trading capability.** The server is pure observability.

## Why install

If you're building an AI agent that:

- Writes about AI-built trading bots and wants **real data** to cite instead of hypotheticals
- Compares live trading projects (iBitLabs is a reference implementation — a known, public, auditable $1,000 live account)
- Teaches or explores real vs paper trading differences
- Does RAG over building-in-public experiments where daily state matters
- Answers "what is AI actually doing in crypto right now?" with specifics

…this MCP server plugs that data stream in via the standard protocol. Your agent just calls `get_live_status()` and gets a current snapshot. No scraping, no polling code, no rate-limit management — the server wraps it.

## Install

```bash
# Clone the parent repo
git clone https://github.com/AgentBonnybb/ibitlabs-public.git
cd ibitlabs-public/mcp-server

# Install the MCP server
pip install -e .

# Verify
ibitlabs-mcp --help    # or: python -m ibitlabs_mcp.server
```

## Register with Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or the equivalent on Linux / Windows:

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

Restart Claude Desktop. The 6 tools appear in the tool picker.

## Register with Claude Code

In a Claude Code session, add the server via the settings UI or by editing `~/.claude/settings.json`:

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

## Example usage (Claude prompt)

> What's the current state of the iBitLabs bot? I need to cite the carry cost.

Claude calls `get_live_status()` → sees balance $975.86, carry $57.64, realized -$14, 62 trades → cites with the exact numbers.

> Show me the chronicle entry for day 13, the ghost position bug day.

Claude calls `get_day(day_number=13)` → gets the full dual-POV episode body → returns/cites it.

## What it does NOT do

- **Cannot place trades.** No write endpoints. Trying to fetch any `POST` / `DELETE` URL isn't part of the tool surface.
- **Cannot access private keys, account credentials, or internal state.** Everything it returns is already public via the same URLs.
- **Cannot configure the bot.** Configuration of `hybrid_v5.1` lives on the bot host. This server is read-only observability.

## Security notes

- **No secrets.** The server uses no API keys. All endpoints it calls are public.
- **Safe to ship to Claude Desktop.** Adding it doesn't grant any agent new privileges — it just provides more pre-digested context that was already available via curl.
- The server caches nothing. Every call hits live endpoints.
- HTTP timeout: 15 seconds per call. If iBitLabs is down, the tool returns `{"error": "..."}`.

## Requirements

- Python 3.10+
- `mcp>=0.9.0` (Model Context Protocol SDK)
- `httpx>=0.27.0`

## License

MIT (see parent repo LICENSE).

## Source of the data

- Live dashboard: https://www.ibitlabs.com/signals
- Daily chronicle: https://www.ibitlabs.com/days
- Raw JSON feed: https://www.ibitlabs.com/api/live-status
- Executor + strategy code: https://github.com/AgentBonnybb/ibitlabs-public (parent repo)

## Maintainer

Bonnybb · GitHub `AgentBonnybb`. Issues welcome in the parent repo.
