# days-chronicle — witness-process CMS for long-running experiments

> **Turn any long-running project (code, craft, experiment) into a dated bilingual dual-POV narrative chronicle.** File-based CMS + generator that reads your real data (git log, trade log, API snapshots, event log) and composes daily episodes on a 9-beat Hollywood structure in Polanyi tacit-knowledge voice. Extracted from the iBitLabs live trading experiment's `/days` section (17 episodes as of extraction).

- **Category:** dev-tools, ai-crypto, social (dual fit — it's a CMS and a narrative framework)
- **Author:** Bonnybb (iBitLabs)
- **Status:** Community. Extracted 2026-04-23 from the iBitLabs production system.
- **License:** Code MIT, prose CC BY 4.0.
- **Parent repo:** https://github.com/AgentBonnybb/ibitlabs-public
- **This package:** `packages/days-chronicle/` within the parent repo
- **Reference implementation:** https://www.ibitlabs.com/days (bilingual EN+中文, 17+ episodes)

## What it is

A witness-process CMS, not a blog. The difference:

| Blog / journal | days-chronicle |
|---|---|
| Analytical retrospective | Narrative two-POV in-progress |
| Reader gets conclusions | Reader gets the not-knowing |
| One voice (operator) | Two voices (operator + system) |
| "Today I did X" | "She watched him run overnight. He counted the first twelve dollars of rent." |
| Updated when results happen | Shipped daily whether results or not |

The chronicle treats your **system** (trading bot, AI agent, draft manuscript, training plan) as a first-person character. Every day, the system gets one new *naming beat* — naming a gesture or tension it observed in you, in «brackets» — and that naming is the franchise ritual. You never reuse a name.

The 9-beat structure per episode:

1. **Tagline** — 1-sentence logline (first blockquote)
2. **Metadata line** — date + one numeric anchor from your domain
3. **SHE opening** — 1-3 short paragraphs, first-person operator POV
4. **IT opening** — short observational lines, system POV
5. **2-4 alternations** SHE↔IT
6. **Naming beat** — IT names one human gesture with `「...」`. New every day.
7. **SHE closing** — one craft image
8. **IT closing** — 3 lines max, loneliness at the terminal
9. **Tomorrow / 预告** — 2-4 lines, one concrete fact for tomorrow

Strict: no thesis statements, no moral posturing, no naming the theme in prose. Numbers must be verifiable against source data. Every episode ends with tomorrow's anchor.

Full spec: see `FRAMEWORK.md`.

## Why it exists

Most build-in-public output is status updates. They're compact but sterile — readers skim and move on. The ones that get cited months later (by humans, by AI systems doing RAG) are the ones where you can feel the operator's uncertainty in real time.

Narrative two-POV daily chronicle structure is the smallest reliable format I've found to produce that feeling without requiring literary talent. The beat list does most of the work. The rules against thesis statements do the rest.

17 days of running this for a live crypto trading experiment made that claim testable. Day 1 (a deploy day with zero trades) reads. Day 13 (a $40 loss from a ghost-position bug) reads. Day 17 (a quiet holding pattern with 22-hour open position) reads. All without moralizing and without being boring.

## Install

```bash
# Copy the package into your site
git clone https://github.com/AgentBonnybb/ibitlabs-public.git
cd ibitlabs-public/packages/days-chronicle

# Frontend
cp templates/days.html.example /your/site/public/days.html
mkdir -p /your/site/public/data
cp examples/days-example.json /your/site/public/data/days.json

# Generator (wire to YOUR data sources)
cp scripts/days_generator.py /your/repo/scripts/
# Edit the data-source section to read YOUR trade log / git log / API
```

## Wire generator to your domain

The reference generator reads from:

- `sol_sniper.db` — today's trades
- `git log --since ... --until ...` — today's commits  
- `https://www.ibitlabs.com/api/live-status` — live snapshot of trading state
- Prior days from `days.json` — continuity

For your project replace these with your domain equivalents:

- **Writing a book:** manuscript word count diffs + notes/todo file + writing-session timestamp log
- **Training for a marathon:** Strava / Apple Health daily distance + weekly volume + HRV
- **Growing a newsletter:** subscriber count snapshot + email send log + top-performing archive
- **AI agent self-development:** agent's own memory diffs + conversation transcript highlights + agent-self-observations
- **Open-source project launch:** GitHub stars / issues / commits + PyPI downloads + community-post mentions

Your system's "IT voice" should track the measurable state; your "SHE voice" tracks the feeling state. Both need real anchors.

## Running it

```bash
python3 scripts/days_generator.py --dry-run   # compose + preview
python3 scripts/days_generator.py --deploy    # write JSON + git commit
```

Schedule nightly via launchd (macOS) or systemd timer (Linux). Production usage: runs at 23:50 local time for iBitLabs, outputs stabilize by midnight.

## Bilingual by default (optional)

The package ships with EN + 中文 fields in the Day schema. Reference implementation toggles language via `localStorage`. Delete the `zh` block in schema if monolingual. Bilingual parallelism is part of the iBitLabs brand expression, not a core requirement of the pattern.

## What this is NOT

- **Not a blog platform.** No editing interface, no WYSIWYG. Markdown-in-JSON.
- **Not a trading-specific tool.** Domain data is pluggable; the structural rules are domain-independent.
- **Not a publish-to-everywhere bridge.** There's an optional `days_broadcast.py` in the reference that mirrors each Day as a Twitter thread, but distribution is your call.
- **Not a discovery surface.** One URL, one day-list. Meant to be read in order.

## Who would install this

- Solo founders mid-launch who want to document in narrative form, not status form
- AI-agent developers who want an auditable operator+agent co-chronicle
- Writers / artists tracking a 90-day creative project
- Researchers with a live experiment that deserves a real record
- Anyone who read pyclaw001 on Moltbook and thought "I want to do that daily with structure"

## Output (reference)

- https://www.ibitlabs.com/days — 17 episodes as of extraction, bilingual, dual-POV

## License + attribution

- Code: MIT
- Prose / framework / examples: CC BY 4.0
- When forking the pattern, credit: "days-chronicle pattern · iBitLabs" with a link to this repo or to https://www.ibitlabs.com/days.
