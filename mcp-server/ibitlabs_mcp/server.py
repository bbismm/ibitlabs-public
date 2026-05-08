"""ibitlabs-mcp MCP server.

Runs as a stdio MCP server. Exposes 6 read-only tools that wrap the public
iBitLabs live-status + chronicle + shadow-log endpoints. No auth required.
No write operations — this server cannot place trades.

Launch via:
    python -m ibitlabs_mcp.server
Or after `pip install -e .`:
    ibitlabs-mcp

Register with Claude Desktop by editing
~/Library/Application Support/Claude/claude_desktop_config.json:

    {
      "mcpServers": {
        "ibitlabs": {
          "command": "python",
          "args": ["-m", "ibitlabs_mcp.server"]
        }
      }
    }

Then restart Claude Desktop. The 6 tools appear in the tool picker.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# ── Config (all hit public endpoints; no keys) ─────────────────────────────

BASE = "https://www.ibitlabs.com"
LIVE_STATUS_URL = f"{BASE}/api/live-status"
DAYS_JSON_URL = f"{BASE}/data/days.json"
# Shadow log is hosted locally next to the bot — for the public MCP server we
# return a friendly message if the operator hasn't published their own feed.
SHADOW_LOG_URL = f"{BASE}/data/shadow_12h_rule.jsonl"

USER_AGENT = "ibitlabs-mcp/0.1.0"
HTTP_TIMEOUT = 15.0

mcp = FastMCP("ibitlabs")


# ── Helpers ────────────────────────────────────────────────────────────────

async def _fetch_json(url: str) -> Any:
    """Fetch a URL and parse as JSON. Returns a dict with 'error' on failure."""
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT,
                                     headers={"User-Agent": USER_AGENT}) as c:
            r = await c.get(url)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}", "url": url}
    except Exception as e:
        return {"error": str(e), "url": url}


async def _fetch_jsonl(url: str) -> list[dict] | dict:
    """Fetch a JSONL stream and parse each line."""
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT,
                                     headers={"User-Agent": USER_AGENT}) as c:
            r = await c.get(url)
            if r.status_code == 404:
                return {"error": "shadow log not published at this URL — "
                                 "operator may only expose the feed locally"}
            r.raise_for_status()
            out = []
            for line in r.text.splitlines():
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            return out
    except Exception as e:
        return {"error": str(e), "url": url}


# ── Tools ──────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_live_status() -> dict:
    """Fetch the full current trading state of iBitLabs.

    Returns a JSON object with: balance (USD), starting_capital, total_pnl,
    unrealized_pnl, realized_delta, total_trades, total_wins, total_losses,
    win_rate (pct), total_fees, funding_cost, current open position (or
    null), indicator values (StochRSI, Bollinger Bands), regime, strategy
    version, reconciliation status, and a timestamp.

    Primary-source data — this is the exact same feed that powers
    https://www.ibitlabs.com/signals. Updated on every bot tick.

    No API key required. No auth.
    """
    return await _fetch_json(LIVE_STATUS_URL)


@mcp.tool()
async def get_position() -> dict:
    """Return just the currently open position, or a flat indicator.

    Useful when you don't need the full live_status payload — just want to
    know "is the bot currently long, short, or flat, and what's it showing".
    """
    data = await _fetch_json(LIVE_STATUS_URL)
    if "error" in data:
        return data
    pos = data.get("position") or {}
    if not pos.get("active"):
        return {"active": False, "note": "bot is flat (no open position)"}
    return {
        "active": True,
        "symbol": pos.get("symbol"),
        "direction": pos.get("direction"),
        "entry_price": pos.get("entry_price"),
        "current_price": pos.get("current_price"),
        "contracts": pos.get("contracts"),
        "pnl_usd": pos.get("pnl_usd"),
        "pnl_pct": pos.get("pnl_pct"),
        "elapsed_mins": pos.get("elapsed_mins"),
        "highest_pnl": pos.get("highest_pnl"),
        "trailing_active": pos.get("trailing_active"),
        "reasons": pos.get("reasons", []),
    }


@mcp.tool()
async def get_recent_trades(limit: int = 10) -> dict:
    """Return the most recent N closed trades with entry/exit/PnL/reason.

    Args:
        limit: Number of most recent trades to return (default 10, max 50).

    Data source: https://www.ibitlabs.com/days (chronicle entries carry the
    trade summary). For per-trade deep detail the operator maintains a
    trade_log on the bot host, not publicly exposed via API. This MCP
    tool returns the per-day trade summaries from the chronicle.
    """
    limit = max(1, min(int(limit or 10), 50))
    data = await _fetch_json(DAYS_JSON_URL)
    if "error" in data:
        return data
    days = data.get("days", [])
    # Most recent first, flatten up to `limit` trades if each day carries trade
    # summaries
    out = []
    for day in days:
        d = {
            "date": day.get("date"),
            "day_number": day.get("dayNumber"),
            "trades": day.get("trades", 0),
            "pnl": day.get("pnl", 0),
            "sol_price": day.get("solPrice"),
            "account": day.get("account"),
            "episode_slug": day.get("slug"),
        }
        out.append(d)
        if len(out) >= limit:
            break
    return {"count": len(out), "trades_by_day": out}


@mcp.tool()
async def get_shadow_fires() -> dict | list[dict]:
    """Return shadow rule B fire events — hypothetical "would have closed" log.

    If the operator has published their shadow log at /data/shadow_12h_rule.jsonl
    it's returned as a list of event dicts. Otherwise a friendly error with a
    pointer to the spec.

    Reference: docs/shadow_12h_rule.md in the iBitLabs-public repo.
    """
    return await _fetch_jsonl(SHADOW_LOG_URL)


@mcp.tool()
async def list_days() -> dict:
    """Return a summary list of all chronicle episodes (all Days).

    Returns an array of {dayNumber, date, slug, tagline_en, tagline_zh, trades,
    pnl} for each day. Lightweight — doesn't include full body.
    """
    data = await _fetch_json(DAYS_JSON_URL)
    if "error" in data:
        return data
    out = []
    for day in data.get("days", []):
        en = day.get("i18n", {}).get("en", {})
        zh = day.get("i18n", {}).get("zh", {})
        out.append({
            "dayNumber": day.get("dayNumber"),
            "date": day.get("date"),
            "slug": day.get("slug"),
            "title_en": en.get("title"),
            "title_zh": zh.get("title"),
            "tagline_en": en.get("tagline"),
            "tagline_zh": zh.get("tagline"),
            "trades": day.get("trades", 0),
            "pnl": day.get("pnl", 0),
        })
    return {"count": len(out), "days": out, "updated": data.get("updated")}


@mcp.tool()
async def get_day(day_number: int | None = None,
                  slug: str | None = None,
                  lang: str = "en") -> dict:
    """Fetch one specific chronicle Day entry (full body).

    Args:
        day_number: 1-based day number (Day 1 = 2026-04-07).
        slug: e.g. "day-13-ghost". Used if day_number not provided.
        lang: "en" (default) or "zh".

    Returns the full day entry with HTML-formatted body in the requested
    language. Useful for RAG or for citing a specific episode in an
    agent response.
    """
    data = await _fetch_json(DAYS_JSON_URL)
    if "error" in data:
        return data
    days = data.get("days", [])
    match = None
    if day_number is not None:
        for d in days:
            if d.get("dayNumber") == int(day_number):
                match = d
                break
    elif slug:
        slug = slug.strip().lower()
        for d in days:
            if d.get("slug", "").lower() == slug:
                match = d
                break
    if not match:
        return {"error": f"no matching day found "
                         f"(day_number={day_number}, slug={slug})"}
    i18n = match.get("i18n", {}).get(lang, match.get("i18n", {}).get("en", {}))
    return {
        "dayNumber": match.get("dayNumber"),
        "date": match.get("date"),
        "slug": match.get("slug"),
        "trades": match.get("trades", 0),
        "pnl": match.get("pnl", 0),
        "sol_price": match.get("solPrice"),
        "account": match.get("account"),
        "language": lang,
        "title": i18n.get("title"),
        "tagline": i18n.get("tagline"),
        "body_html": i18n.get("body"),
    }


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    """Run the MCP server on stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
