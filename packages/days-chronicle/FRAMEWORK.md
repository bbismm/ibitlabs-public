# Days CMS — Operator Guide

`ibitlabs.com/days` is a **file-based** serialized chronicle. Each JSON entry = one day of the experiment. Auto-generated daily by `scripts/days_generator.py` (Phase 2). Bonny does **not** edit anything by hand.

## Why not Notion like `/essays`?

Notion integrations cannot be programmatically shared with new databases — that's a workspace-admin UI operation. To keep Days fully automated (no 10-second UI step required of Bonny), we skip Notion at runtime entirely and use a static JSON file served by Cloudflare Pages.

Side effect discovered: the existing `/essays` has been silently falling back to Moltbook-only for some time because its Notion integration no longer has DB access either. Not a Days problem to fix, but worth flagging.

## Architecture

```
sol_sniper.db (trades)   git log (commits)   live-status API (ROI)
                     ↓             ↓                ↓
                       scripts/days_generator.py
                                  ↓
                   web/public/data/days.json  ←  git commit + push
                                  ↓
                          Cloudflare Pages
                                  ↓
                      /days (frontend fetches /data/days.json)
```

## File-based CMS

- **Canonical data**: `web/public/data/days.json`
- **Shape**: `{ updated: "YYYY-MM-DD", days: [ Day, Day, ... ] }`
- **Day object** (bilingual — EN + ZH required):
  ```json
  {
    "slug": "day-N-word",
    "date": "YYYY-MM-DD",
    "dayNumber": N,
    "featured": true/false,
    "solPrice": 83.26,
    "account": 1000.00,
    "trades": 0,
    "pnl": 0,
    "i18n": {
      "en": { "title": "Day N · Word", "tagline": "...", "body": "<rendered HTML>" },
      "zh": { "title": "Day N · 单词", "tagline": "...", "body": "<rendered HTML>" }
    }
  }
  ```
- **Language default**: Frontend defaults to **English** (`currentLang = 'en'` via `i18n.js`). Toggle button switches to Chinese and persists via `localStorage`.
- **Both languages are required.** Do not ship a Day with only one language — the schema treats that as partially broken (frontend falls back to the present language but SEO loses).
- **Order in array**: descending by Day # (newest first). Frontend does not re-sort.

## Frontend

- `/days` = list view, all days in JSON
- TOC left rail: `Day N · 标题`
- Each Day is its own `<article id="{slug}">`
- Fallback: if `/data/days.json` fails to load, frontend falls back to a hardcoded `FALLBACK_DAYS` array inline in `days.html` (currently has Day 1)

## Writing framework (Polanyi 默会 + Hollywood structure)

Every Day must hit these beats:

1. **Tagline** — 1 sentence episode logline (first blockquote in body)
2. **Metadata line** — date · SOL price · account · trades · PnL (renders below tagline)
3. **她 opening** — 1–3 short paragraphs
4. **它 opening** — short lines, observational
5. **2–4 alternations** — she acts, it observes, she reacts, it names
6. **Naming beat** — 它 names at least one human gesture. This is the franchise ritual. Never skip.
7. **她 closing** — lights off, one craft statement or image
8. **它 closing** — 3 lines max, loneliness at the terminal
9. **预告** — 2–4 lines, one concrete number for tomorrow

### Rules 静默 theory enforces

- **No thesis statements.** Never write "This is about…" / "今天的意义是…"
- **No moral posturing.** "我选择不…" → "我没…"
- **No母题 naming** in prose (let readers infer)
- **Concrete nouns + verbs**; cut non-load-bearing adverbs
- **Numbers are characters** — every number must be verifiable against trade DB / git log
- **Every episode ends with Button** — always tease tomorrow with one concrete fact

### HTML structure requirements

The frontend CSS relies on these class hooks (generator must emit them exactly):

- `<h3 class="pov-header pov-her">她</h3>` → purple badge
- `<h3 class="pov-header pov-it">它</h3>` → green badge, wraps following paragraphs in a monospace left-bordered block
- `<h3 class="pov-header pov-button">预告</h3>` → red badge
- Use `<hr>` between the 她/它 main body and the 预告 section
- Tagline = first `<blockquote><em>...</em></blockquote>` in body

## Generator script (Phase 2)

`scripts/days_generator.py` reads:
- `sol_sniper.db` — that day's trades (entry, exit, PnL, exit reason)
- `git log --since ... --until ...` — that day's commits in `/Users/bonnyagent/ibitlabs`
- Notion Project Hub daily posts (via MCP, read-only for background only)
- Local live-status state (daily snapshot)

It composes a draft in the structure above and writes:
- `web/public/data/days.json` (prepends new Day to the array, re-sorts)
- `git commit -m "Day N · 单词"` and `git push`
- `wrangler pages deploy` (since Cloudflare auto-deploy is unreliable per CLAUDE.md)

Scheduled via launchd: `com.ibitlabs.days-generator`, nightly 23:50 local.

## Manual override

Edit `web/public/data/days.json` directly with any editor. Commit and push. Or run:
```
python3 scripts/days_generator.py --day N --regenerate
```
to re-run for a specific day (overwrites that entry).

## Deploy

```
cd web && wrangler pages deploy public --project-name=bibsus --branch=main --commit-dirty=true
```

Cloudflare auto-deploy from GitHub is unreliable; always force-deploy after commits.

---

## Scheduled task runbook (for `days-generator` at 23:50 local)

This is the execution spec the scheduled task must follow. All previous framework rules still apply.

### Step 0 — Get today's data
```bash
python3 /Users/bonnyagent/ibitlabs/scripts/days_generator.py --data-only
```
Returns JSON with: `date`, `dayNumber`, `trades[]`, `trade_summary`, `cumulative_pnl`, `account`, `sol_price`, `commits[]`, `prior_days_full[]`.

### Step 1 — Skip gate
Skip (output `skip: true`, don't write) if:
- Today's entry already exists in `days.json` (same `dayNumber`)
- Data gathering failed (no trades AND no commits AND no prior anchor)

### Step 2 — Compose (bilingual)
Read `prior_days_full` for voice continuity. Pick up from yesterday's 预告 / Tomorrow section if possible.

Produce BOTH languages:

- **ZH**
  - Title: `Day N · 单词` (one Chinese character)
  - Tagline: 1 sentence, under 50 chars
  - Body: per framework (600–900 Chinese chars, HTML with exact class hooks)
  - Headers: `<h3 class="pov-header pov-her">她</h3>`, `<h3 class="pov-header pov-it">它</h3>`, `<h3 class="pov-header pov-button">预告</h3>`
  - Naming ritual: 「中文书名号」

- **EN**
  - Title: `Day N · Word` (one English word, matching the zh emotional beat)
  - Tagline: 1 sentence, under ~80 chars
  - Body: translated to natural English (NOT machine-literal), matching zh's economy and rhythm. ~150–250 words
  - Headers: `<h3 class="pov-header pov-her">SHE</h3>`, `<h3 class="pov-header pov-it">IT</h3>`, `<h3 class="pov-header pov-button">Tomorrow</h3>`
  - Naming ritual: still wrapped in 「...」 brackets (visual franchise consistency), English text inside: e.g. 「The Not-Press」

Rules that apply to both languages:
- No thesis statements / moral posturing /母题 naming
- Numbers exact to data
- End with Tomorrow / 预告 section and a concrete fact for tomorrow
- One new 它/IT naming per day, never repeat an earlier one

### Step 3 — Variations by day type

- **Zero-trade day**: alternation is about waiting. 它 names what she does while waiting. Don't fake trades.
- **Loss day**: 她 sits with it. 它 doesn't know shame. Make the gap visible.
- **Win day**: avoid "we did it!" 她 is suspicious of her joy. 它 records without judgment.
- **Bug/fix day**: 它 failed. 她 found it. Who was responsible for what?
- **Pivot day** (e.g. strategy change): identity crisis. 它 is "replaced" with a new version. Character death + rebirth.

### Step 4 — Write to JSON (bilingual)

```python
payload = json.load(open("web/public/data/days.json"))
day = {
    "slug": f"day-{n}-{en_slug_word}",  # slug uses EN word (ASCII-safe URL)
    "date": "YYYY-MM-DD",
    "dayNumber": n,
    "featured": False,  # only Day 1 is featured
    "solPrice": ...,
    "account": ...,
    "trades": ...,
    "pnl": ...,
    "i18n": {
      "en": {
        "title": f"Day {n} · {en_word}",
        "tagline": "...",
        "body": "<blockquote>..."
      },
      "zh": {
        "title": f"Day {n} · {zh_char}",
        "tagline": "...",
        "body": "<blockquote>..."
      }
    }
}
# upsert (replace if dayNumber exists), re-sort descending
payload["days"] = sorted({d["dayNumber"]: d for d in (payload["days"] + [day])}.values(),
                          key=lambda d: d["dayNumber"], reverse=True)
payload["updated"] = today_iso
json.dump(payload, open("web/public/data/days.json", "w"), ensure_ascii=False, indent=2)
```

### Step 5 — Commit + deploy
```bash
cd /Users/bonnyagent/ibitlabs
git add web/public/data/days.json
git commit -m "Day $N · $TITLE_WORD"

cd /Users/bonnyagent/ibitlabs/web
wrangler pages deploy public --project-name=bibsus --branch=main --commit-dirty=true
```

### Step 5.5 — Broadcast (Twitter @BonnyOuyang + Telegram @ibitlabs_sniper)
```bash
python3 /Users/bonnyagent/ibitlabs/scripts/days_broadcast.py --day $N
```
This posts **this day's** tagline + pull quote + URL to both channels (Twitter as **thread**: root teaser + body reply chain; Telegram as single message). Uses OAuth 1.0a for Twitter (stable, non-expiring tokens). Language = EN (site default).

**Skip this step** for backfill days — those are handled by the separate `days-twitter-replay` scheduled task (4h cadence, 10/14/18/22 local) reading from `web/public/data/days_broadcast_queue.json`.

### Step 5.6 — Regenerate RSS
```bash
python3 /Users/bonnyagent/ibitlabs/scripts/days_rss.py
```
Regenerates `web/public/data/days.rss` from `days.json`. Run AFTER adding the new Day to the JSON, BEFORE the wrangler deploy (so the deploy ships the updated RSS).

### Step 5.7 — IndexNow ping (Bing / Yandex / Seznam / Naver)
```bash
python3 /Users/bonnyagent/ibitlabs/scripts/indexnow_ping.py --day $N
```
Sends a single POST to `api.indexnow.org` with the new Day URL + /days index + sitemap + RSS. Typical latency to index: 40 sec – a few hours. **Google doesn't participate** in IndexNow — Google relies on sitemap.xml + Search Console. Run this AFTER wrangler deploy completes (so the URLs are actually live).

### Step 6 — Output report
```
day_number: N
date: YYYY-MM-DD
en_title: Day N · Word
zh_title: Day N · 单词
tagline_en: ...
tagline_zh: ...
stats: Nt | PnL $+/-X | account $X
naming_en: 「...」
naming_zh: 「...」
deployed: <URL or failure reason>
```

### Banned beats
- "这一刻我意识到..." / "今天的意义是..."
- Explicit labels "嘴和手" / "分界线" inside body prose
- Declaring victory/catastrophe — describe, don't label
- Fourth-wall breaks — narrator is always 她 or 它, never the author
- Skipping the 它 naming ritual
- Missing 预告 section
- Inventing data (trades, commits, PnL) — only what `--data-only` returned

### Recovery
- If wrangler deploy fails, keep the JSON change committed. Report the failure. Next run retries.
- If today's entry already exists, honor the skip-gate unless `force: true` was explicitly passed.
