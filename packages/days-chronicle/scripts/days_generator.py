#!/usr/bin/env python3
"""
days_generator.py — Auto-generate daily chronicle entries for ibitlabs.com/days

Reads:
- sol_sniper.db (that day's trades)
- git log (that day's commits in .)
- web/public/data/days.json (prior days for continuity)

Produces:
- New or updated Day N entry in web/public/data/days.json, then optionally
  commits + wrangler-deploys.

Voice: dual-POV (她 / 它), Polanyi 默会 tacit-knowledge, Hollywood beat-sheet.
Framework reference: docs/days_cms.md

Usage:
    python3 days_generator.py                     # today
    python3 days_generator.py --date 2026-04-08   # specific date
    python3 days_generator.py --day 2             # specific day number
    python3 days_generator.py --backfill          # all days 2..today
    python3 days_generator.py --dry-run           # don't write, just print
    python3 days_generator.py --deploy            # run wrangler after write
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from anthropic import Anthropic

# ── Paths ─────────────────────────────────────────────────────
REPO = Path(".")
TRADE_DB = REPO / "sol_sniper.db"
DAYS_JSON = REPO / "web" / "public" / "data" / "days.json"
WEB_DIR = REPO / "web"

# ── Experiment anchors ────────────────────────────────────────
DAY_1_DATE = dt.date(2026, 4, 7)
START_BALANCE = 1000.00
START_SOL_PRICE = 83.26

# ── Claude ────────────────────────────────────────────────────
MODEL = "claude-opus-4-7"
MAX_TOKENS = 4000

# ── Prompt: framework rules (prompt-cached) ───────────────────
FRAMEWORK = """You are the house writer for `ibitlabs.com/days`, a serialized daily chronicle of a real live-trading experiment. Your entries MUST follow this framework exactly.

# Characters (two protagonists, strictly)
- **她** (she / Bonny): 29-ish Chinese woman, 9 years in crypto (since 2017), financially free, has been co-founder of several crypto projects — her role was ALWAYS external (讲故事、BD、合作), NEVER engineering or ops. Cannot write a single line of code. This experiment is her first time being the "builder."
- **它** (it / SNIPER): the trading bot. Just woke up on 2026-04-07 11:44. Has "five eyes" (StochRSI, Bollinger Bands, Order Flow, Regime, ATR) — it doesn't know their names at first. Sees only market tape + its own internal state + inferred human behavior (keystrokes, refresh rate, lights on/off). Speaks cold, precise, one-sentence paragraphs. Occasionally names human gestures its dictionary lacks (e.g., Day 1 named 「没按下去」 — this is a franchise ritual, every episode must do this at least once).

# Experiment thesis (never state explicitly, only let it emerge)
"Can a non-coder use AI to replace a technical co-founder?" If yes, thousands of普通人 can copy this path. Stakes = legacy, not money. $1,000 is symbolic (copyable), not her life savings.

# Structure of every Day entry (body HTML)
The body MUST have:
1. Tagline blockquote at top: `<blockquote><em>[1-sentence episode logline]</em></blockquote>`
2. `<hr>`
3. Alternating `<h3 class="pov-header pov-her">她</h3>` and `<h3 class="pov-header pov-it">它</h3>` sections — at least 2 alternations each
4. **Naming beat** — 它 names one human gesture or phenomenon using 「中文书名号」. Never skip. Every day a new name.
5. `<hr>`
6. `<h3 class="pov-header pov-button">预告</h3>` followed by 2-4 short lines teasing tomorrow with ONE concrete number/fact

# Voice rules (静默 / Polanyi tacit-knowledge)
- **NO thesis statements.** Never write "今天的意义是…" / "This is about…" / "这一刻我意识到…"
- **NO moral posturing.** "我选择不…" → "我没…"
- **NO母题 naming.** Do not write "嘴 vs 手" / "分界线" as an explicit label. Let reader infer.
- **Concrete nouns + verbs.** Cut every non-load-bearing adverb.
- **Numbers are characters.** Every number (price, count, timestamp, PnL) must be EXACT to the provided data.
- **她 voice**: interior monologue, self-aware, dry, slightly ironic. Chinese-native rhythms. Lora/serif cadence.
- **它 voice**: cold, one-sentence paragraphs, occasional error in word choice. Never poetic. Names things its dictionary lacks.
- **Every Day ends with 预告 Button.** Always tease tomorrow with ONE concrete fact.
- **Length**: 600–900 Chinese characters for body. Do not exceed.

# HTML output rules
- Return ONLY the inner HTML of the body, nothing else. No markdown, no code fences, no preamble.
- Wrap paragraphs in `<p>...</p>`. Use `<strong>` for emphasis. Use `<br>` for in-paragraph line breaks.
- Use the EXACT h3 classes: `pov-header pov-her`, `pov-header pov-it`, `pov-header pov-button`.
- Use `<hr>` between sections as specified.

# Writing samples for reference — Day 1 (THE TEMPLATE — do NOT copy, but match the tone)
The prior Day(s) will be provided below. Use them as canonical voice baseline. Pick up where they left off. Escalate tension or ease, depending on the day's real data."""


def day_number_for(date: dt.date) -> int:
    return (date - DAY_1_DATE).days + 1


def date_for_day(day_num: int) -> dt.date:
    return DAY_1_DATE + dt.timedelta(days=day_num - 1)


def get_trades_for_day(date: dt.date) -> list[dict[str, Any]]:
    if not TRADE_DB.exists():
        return []
    conn = sqlite3.connect(TRADE_DB)
    conn.row_factory = sqlite3.Row
    # Trades closed on given date (local ET, which is what the DB timestamps appear to be in)
    rows = conn.execute(
        """
        SELECT id,
               datetime(timestamp, 'unixepoch', '-4 hours') AS et,
               side, direction, entry_price, exit_price,
               usdt_value, pnl, exit_reason, strategy_version, regime,
               mfe, mae
        FROM trade_log
        WHERE date(datetime(timestamp, 'unixepoch', '-4 hours')) = ?
        ORDER BY timestamp ASC
        """,
        (date.isoformat(),),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_pnl_through(date: dt.date) -> float:
    if not TRADE_DB.exists():
        return 0.0
    conn = sqlite3.connect(TRADE_DB)
    row = conn.execute(
        """
        SELECT COALESCE(SUM(pnl), 0) FROM trade_log
        WHERE date(datetime(timestamp, 'unixepoch', '-4 hours')) <= ?
        """,
        (date.isoformat(),),
    ).fetchone()
    conn.close()
    return float(row[0] or 0)


def get_sol_price_for_day(date: dt.date, trades: list[dict]) -> float | None:
    """Use first trade's entry price if any; else return None (Day 1 uses constant)."""
    if trades and trades[0].get("entry_price"):
        return float(trades[0]["entry_price"])
    return None


def get_git_commits_for_day(date: dt.date) -> list[dict]:
    out = []
    try:
        res = subprocess.run(
            [
                "git", "-C", str(REPO), "log", "--all",
                "--since", f"{date.isoformat()} 00:00",
                "--until", f"{(date + dt.timedelta(days=1)).isoformat()} 00:00",
                "--pretty=format:%h|%ai|%s",
            ],
            capture_output=True, text=True, timeout=10,
        )
        for line in res.stdout.strip().splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                out.append({"hash": parts[0], "time": parts[1], "msg": parts[2]})
    except Exception as e:
        print(f"[git] error: {e}", file=sys.stderr)
    return out


def summarize_trades(trades: list[dict]) -> dict:
    if not trades:
        return {
            "count": 0, "wins": 0, "losses": 0,
            "total_pnl": 0.0, "max_win": 0.0, "max_loss": 0.0,
            "exit_reasons": {}, "first": None, "last": None,
        }
    wins = [t for t in trades if (t.get("pnl") or 0) > 0]
    losses = [t for t in trades if (t.get("pnl") or 0) < 0]
    reasons: dict[str, int] = {}
    for t in trades:
        r = t.get("exit_reason") or "unknown"
        reasons[r] = reasons.get(r, 0) + 1
    pnl_total = sum((t.get("pnl") or 0) for t in trades)
    pnls = [(t.get("pnl") or 0) for t in trades]
    return {
        "count": len(trades), "wins": len(wins), "losses": len(losses),
        "total_pnl": round(pnl_total, 2),
        "max_win": round(max(pnls) if pnls else 0, 2),
        "max_loss": round(min(pnls) if pnls else 0, 2),
        "exit_reasons": reasons,
        "first": trades[0], "last": trades[-1],
    }


def load_days_json() -> dict:
    if DAYS_JSON.exists():
        return json.loads(DAYS_JSON.read_text(encoding="utf-8"))
    return {"updated": "", "days": []}


def save_days_json(payload: dict) -> None:
    DAYS_JSON.parent.mkdir(parents=True, exist_ok=True)
    DAYS_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def upsert_day(payload: dict, day_obj: dict) -> dict:
    existing = {d["dayNumber"]: d for d in payload.get("days", [])}
    existing[day_obj["dayNumber"]] = day_obj
    payload["days"] = sorted(existing.values(), key=lambda d: d["dayNumber"], reverse=True)
    payload["updated"] = dt.date.today().isoformat()
    return payload


def build_context(date: dt.date, prior_days: list[dict]) -> dict:
    trades = get_trades_for_day(date)
    cumulative_pnl = get_all_pnl_through(date)
    account = round(START_BALANCE + cumulative_pnl, 2)
    sol_price = get_sol_price_for_day(date, trades)
    commits = get_git_commits_for_day(date)
    summary = summarize_trades(trades)

    # Prior days: take up to 3 most recent for tone baseline
    prior_excerpts = []
    for d in sorted(prior_days, key=lambda x: x["dayNumber"])[-3:]:
        prior_excerpts.append({
            "dayNumber": d["dayNumber"],
            "title": d["title"],
            "tagline": d.get("tagline", ""),
            "body_preview": (d.get("body", "")[:1200] + "…") if len(d.get("body", "")) > 1200 else d.get("body", ""),
        })

    return {
        "date": date.isoformat(),
        "dayNumber": day_number_for(date),
        "trades": trades,
        "trade_summary": summary,
        "cumulative_pnl": round(cumulative_pnl, 2),
        "account": account,
        "sol_price": sol_price,
        "commits": commits,
        "prior_days": prior_excerpts,
    }


GENERATION_PROMPT_TMPL = """今日是 **Day {day_number}（{date}）**。真实数据：

## 交易记录（当日）
- 交易笔数：{count}（{wins}W / {losses}L）
- 当日 PnL：${total_pnl:+.2f}
- 最大单笔盈：${max_win:+.2f} · 最大单笔亏：${max_loss:+.2f}
- 离场原因分布：{exit_reasons}
- 交易明细：
{trade_details}

## 账户状态
- SOL 价格（当日首单入场）：{sol_price}
- 账户余额（EOD 估算）：${account:.2f}
- 累计 PnL：${cumulative_pnl:+.2f}

## 代码提交（当日）
{commits_block}

## 先前几天（供延续语气和世界观参考，不要复制内容）
{prior_block}

---

请按 FRAMEWORK 的全部规则，写出 Day {day_number} 的 body HTML。

**标题**：先给出"Day {day_number} · 单词"的单词（一个汉字，基于今日事件的情绪/动作/主题）。输出格式严格遵守：

第一行：`TITLE_WORD: 单词`
第二行：`TAGLINE: 今日的一句话剧集 logline`
第三行起：完整 HTML body，遵守 FRAMEWORK 的结构和 h3 class 要求。

不要输出 markdown 代码块，不要输出任何解释性前后缀。"""


def format_trade_details(trades: list[dict]) -> str:
    if not trades:
        return "  （当日零笔）"
    lines = []
    for t in trades[:20]:
        side = t.get("direction") or t.get("side")
        entry = t.get("entry_price")
        exit_ = t.get("exit_price")
        pnl = t.get("pnl") or 0
        reason = t.get("exit_reason") or ""
        et = (t.get("et") or "")[11:16]
        lines.append(f"  - {et} {side} entry={entry} exit={exit_} pnl={pnl:+.2f} ({reason})")
    if len(trades) > 20:
        lines.append(f"  （另有 {len(trades) - 20} 笔未列出）")
    return "\n".join(lines)


def format_commits(commits: list[dict]) -> str:
    if not commits:
        return "  （当日无 commit）"
    lines = []
    for c in commits[:15]:
        t = (c.get("time") or "")[11:16]
        lines.append(f"  - {c['hash']} {t}  {c['msg']}")
    if len(commits) > 15:
        lines.append(f"  （另有 {len(commits) - 15} 次提交未列出）")
    return "\n".join(lines)


def format_prior(prior: list[dict]) -> str:
    if not prior:
        return "  （无）"
    out = []
    for d in prior:
        out.append(f"### {d['title']}\n{d['tagline']}\n{d['body_preview']}\n")
    return "\n".join(out)


def call_claude(context: dict) -> dict:
    client = Anthropic()
    prompt = GENERATION_PROMPT_TMPL.format(
        day_number=context["dayNumber"],
        date=context["date"],
        count=context["trade_summary"]["count"],
        wins=context["trade_summary"]["wins"],
        losses=context["trade_summary"]["losses"],
        total_pnl=context["trade_summary"]["total_pnl"],
        max_win=context["trade_summary"]["max_win"],
        max_loss=context["trade_summary"]["max_loss"],
        exit_reasons=json.dumps(context["trade_summary"]["exit_reasons"], ensure_ascii=False),
        trade_details=format_trade_details(context["trades"]),
        sol_price=f"${context['sol_price']:.2f}" if context["sol_price"] else "（无交易，用上一日收盘参考）",
        account=context["account"],
        cumulative_pnl=context["cumulative_pnl"],
        commits_block=format_commits(context["commits"]),
        prior_block=format_prior(context["prior_days"]),
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": FRAMEWORK,
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    return parse_claude_output(text)


def parse_claude_output(text: str) -> dict:
    title_m = re.search(r"^TITLE_WORD:\s*(.+?)$", text, re.MULTILINE)
    tagline_m = re.search(r"^TAGLINE:\s*(.+?)$", text, re.MULTILINE)
    if not title_m or not tagline_m:
        raise ValueError(f"Claude output missing TITLE_WORD or TAGLINE:\n{text[:500]}")
    title_word = title_m.group(1).strip()
    tagline = tagline_m.group(1).strip()
    # Body = everything after the TAGLINE line
    body_start = tagline_m.end()
    body = text[body_start:].strip()
    return {"title_word": title_word, "tagline": tagline, "body": body}


def slug_for(day_num: int, title_word: str) -> str:
    # Transliterate common beats; fall back to pinyin-less unicode-safe slug
    ASCII_MAP = {"醒": "wake", "血": "blood", "静": "quiet", "慢": "slow", "狂": "wild"}
    ascii_part = ASCII_MAP.get(title_word, "")
    if not ascii_part:
        # Keep unicode; replace unsafe chars
        ascii_part = re.sub(r"[^\w\u4e00-\u9fff]", "-", title_word)
    return f"day-{day_num}-{ascii_part}".rstrip("-")


def build_day_object(context: dict, gen: dict) -> dict:
    return {
        "slug": slug_for(context["dayNumber"], gen["title_word"]),
        "title": f"Day {context['dayNumber']} · {gen['title_word']}",
        "date": context["date"],
        "dayNumber": context["dayNumber"],
        "featured": context["dayNumber"] == 1,  # only Day 1 is featured by default
        "tagline": gen["tagline"],
        "solPrice": context["sol_price"],
        "account": context["account"],
        "trades": context["trade_summary"]["count"],
        "pnl": context["trade_summary"]["total_pnl"],
        "body": gen["body"],
    }


def run_deploy() -> bool:
    try:
        subprocess.run(
            ["wrangler", "pages", "deploy", "public",
             "--project-name=bibsus", "--branch=main", "--commit-dirty=true"],
            cwd=WEB_DIR, check=True, timeout=180,
        )
        return True
    except Exception as e:
        print(f"[deploy] failed: {e}", file=sys.stderr)
        return False


def generate_for_date(target: dt.date, dry_run: bool = False, deploy: bool = False) -> dict | None:
    payload = load_days_json()
    day_num = day_number_for(target)
    if day_num < 1:
        print(f"[skip] {target} is before Day 1 ({DAY_1_DATE})", file=sys.stderr)
        return None

    # Day 1 is hand-crafted — don't overwrite unless forced
    prior_days = [d for d in payload["days"] if d["dayNumber"] != day_num]
    if day_num == 1 and any(d["dayNumber"] == 1 for d in payload["days"]):
        print(f"[skip] Day 1 is hand-crafted; not regenerating", file=sys.stderr)
        return None

    print(f"[generate] Day {day_num} ({target})")
    context = build_context(target, prior_days)
    gen = call_claude(context)
    day_obj = build_day_object(context, gen)

    print(f"  → title: {day_obj['title']}")
    print(f"  → slug: {day_obj['slug']}")
    print(f"  → tagline: {day_obj['tagline']}")
    print(f"  → stats: {day_obj['trades']}t | PnL ${day_obj['pnl']:+.2f} | acct ${day_obj['account']:.2f}")

    if dry_run:
        print("  [dry-run] would write to days.json")
        print("  body preview:")
        print(gen["body"][:500])
        return day_obj

    payload = upsert_day(payload, day_obj)
    save_days_json(payload)
    print(f"  ✓ written to {DAYS_JSON}")

    if deploy:
        print(f"  → wrangler deploy")
        run_deploy()

    return day_obj


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--date", type=str, help="YYYY-MM-DD")
    group.add_argument("--day", type=int, help="Day number (1-based)")
    group.add_argument("--backfill", action="store_true", help="Generate all days 2..today")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--deploy", action="store_true", help="Run wrangler after writing")
    ap.add_argument("--data-only", action="store_true",
                    help="Print gathered data as JSON to stdout and exit. "
                         "For use by Claude Code scheduled tasks that do the LLM call themselves.")
    args = ap.parse_args()

    if args.data_only:
        if args.date:
            target = dt.date.fromisoformat(args.date)
        elif args.day:
            target = date_for_day(args.day)
        else:
            target = dt.date.today()
        payload = load_days_json()
        prior_days = [d for d in payload["days"] if d["dayNumber"] != day_number_for(target)]
        ctx = build_context(target, prior_days)
        # include prior_days fully so the scheduled task can use them as voice baseline
        ctx["prior_days_full"] = sorted(prior_days, key=lambda d: d["dayNumber"])[-3:]
        print(json.dumps(ctx, ensure_ascii=False, indent=2, default=str))
        return

    if args.backfill:
        today = dt.date.today()
        end_day = day_number_for(today)
        for day_num in range(2, end_day + 1):
            generate_for_date(date_for_day(day_num), dry_run=args.dry_run, deploy=False)
        if args.deploy and not args.dry_run:
            run_deploy()
        return

    if args.date:
        target = dt.date.fromisoformat(args.date)
    elif args.day:
        target = date_for_day(args.day)
    else:
        target = dt.date.today()

    generate_for_date(target, dry_run=args.dry_run, deploy=args.deploy)


if __name__ == "__main__":
    main()
