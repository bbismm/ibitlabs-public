"""ibitlabs-mcp — MCP server exposing iBitLabs live trading data.

Gives any MCP-compatible agent (Claude Desktop, Claude Code, OpenClaw, Codex,
or any framework supporting the Model Context Protocol) access to the live
state of the iBitLabs trading experiment as callable tools.

Tools exposed:
  - get_live_status:  Full live-status JSON (balance, position, PnL, fees, funding, trades, WR)
  - get_position:     Just the currently open position (or None)
  - get_recent_trades: Last N closed trades with entry/exit/PnL/reason
  - get_shadow_fires:  Shadow rule B log entries (hypothetical close events)
  - list_days:         Summary of all chronicle episodes
  - get_day:           One specific chronicle Day entry (by number or slug)

All tools hit public, un-authenticated endpoints — no API keys required.
"""
__version__ = "0.1.0"
