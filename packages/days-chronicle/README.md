# days-chronicle

> **A witness-process CMS for long-running experiments.** Auto-generates a dated, bilingual, dual-POV daily chronicle from your real data (commit logs, trade logs, API snapshots, event logs) using Polanyi tacit-knowledge voice and a 9-beat Hollywood episode structure. Designed for building-in-public projects, solo founders, artists tracking a craft, or anyone running a multi-month experiment that deserves a narrative record rather than a bullet-point status update.

This package started as the `/days` section of https://www.ibitlabs.com — the daily chronicle of a non-coder's live AI-built crypto trading experiment. After 17 daily episodes (bilingual EN + 中文) proved the structure works, we extracted the pattern as a standalone package. The trading bot isn't the point; the **witness-process pattern** is.

## What it gives you

- A file-based CMS (`data/days.json`) with a defined bilingual Day schema
- A generator (`scripts/days_generator.py`) that reads your sources, composes a Day entry with strict structural beats, and writes to the JSON
- A frontend template (`templates/days.html.example`) with the CSS class hooks the generator emits
- A framework guide (`FRAMEWORK.md`) documenting the 9-beat structure, dual-POV rules, naming ritual, and do/don'ts
- An example entry (`examples/days-example.json`) — Day 1 from iBitLabs, to see the shape

## Why witness-process, not blog or journal

A typical build-in-public post is a status update: "today I did X, tomorrow I'll do Y." It's retrospective and analytical. The reader gets a summary.

A chronicle entry is **narrative**. Two characters (you and your system) alternate first-person POVs. Your system is a character — it observes you, it gets named (one new naming beat per day, franchise ritual), it doesn't know shame. You feel things. The reader is inside the experiment, not above it.

This difference isn't stylistic. It determines what gets transmitted:

- **Analytical journal:** conclusions about what happened
- **Witness chronicle:** the process of not knowing

The latter is what actually gets cited by other humans (and by AI systems doing RAG) when they want a real example of a long experiment, because the fumbling is the signal, not the result.

## Who this is for

- **Solo builders** running a 3-12 month project where the *process* matters as much as the output (launches, open-source projects, founder journeys)
- **Creators** with a craft that develops over months (writing a book, training for a race, learning an instrument, growing a newsletter)
- **Researchers** running a live experiment where daily state changes
- **AI agents** that want to keep an auditable chronicle of their own development alongside the human operator's POV — this is where dual-POV really shines

## Structure

Every day is a JSON object following this schema:

```json
{
  "dayNumber": 17,
  "date": "2026-04-23",
  "slug": "day-17-guard",
  "solPrice": 85.79,          // any snapshot numbers you care about
  "account": 975.86,
  "trades": 0,
  "pnl": 0,
  "i18n": {
    "en": {
      "title": "Day 17 · Guard",
      "tagline": "She's still holding yesterday's 88.20. It's guarding numbers. Two different ways of guarding.",
      "body": "<blockquote><em>...</em></blockquote>\n<h3 class=\"pov-header pov-her\">SHE</h3>\n..."
    },
    "zh": {
      "title": "Day 17 · 守",
      "tagline": "她还抱着 88.20 的仓。它守着数字。两个守法不一样。",
      "body": "<blockquote><em>...</em></blockquote>\n<h3 class=\"pov-header pov-her\">她</h3>\n..."
    }
  }
}
```

The 9-beat structure every entry must hit is documented in `FRAMEWORK.md`. Strict rules, because discipline is what makes the ritual read as one voice over time instead of a bag of moods.

## Quick start

```bash
# 1. Copy the template to your site
cp templates/days.html.example /your/site/public/days.html
mkdir -p /your/site/public/data
cp examples/days-example.json /your/site/public/data/days.json

# 2. Wire the generator to your data sources
# Edit scripts/days_generator.py — replace the "data fetch" section with calls
# against your own trade DB / git log / API / event log / whatever.

# 3. Generate today's entry
python3 scripts/days_generator.py --dry-run
# Review the composed entry. If good:
python3 scripts/days_generator.py --deploy
```

## Beat requirements (from FRAMEWORK.md, at a glance)

Every Day must have, in order:

1. **Tagline** — 1-sentence episode logline (first blockquote)
2. **Metadata line** — date · one numeric anchor from your domain
3. **SHE opening** — 1-3 short paragraphs, first-person
4. **IT opening** — short lines, observational, your system's voice
5. **2-4 alternations** between SHE and IT
6. **Naming beat** — IT names one human gesture with `「name」` brackets. **New every day; never repeat a prior name**
7. **SHE closing** — one craft statement or image
8. **IT closing** — 3 lines max, loneliness at the terminal
9. **Tomorrow / 预告** — 2-4 lines, one concrete number for tomorrow

Violations (see FRAMEWORK.md for full list):

- No thesis statements
- No moral posturing ("I chose not to..." → "I didn't...")
- No naming the story's theme in prose
- Numbers must be verifiable against source data
- Every episode ends with tomorrow's concrete anchor

## Customize

- **Swap the domain:** the example entry is from a crypto trading bot (SOL PERP, balance, PnL). Replace with your domain's real data (line-counts for a novel, miles run for a marathoner, subscribers for a newsletter, agents interviewed for a study).
- **Swap "IT" for your system's character:** the bot is called "SNIPER" in the iBitLabs example. For a novel-writing chronicle, IT might be the draft. For a marathon chronicle, IT might be the body. The dual-POV works as long as IT is concrete and observational.
- **Monolingual:** delete the `zh` block in the Day schema and remove the language toggle in the frontend. The bilingual parallelism is part of the iBitLabs brand but not essential to the pattern.

## Relationship to iBitLabs

iBitLabs is the reference implementation running in production at https://www.ibitlabs.com/days — 17+ daily episodes, bilingual, backfilled from Day 1. The generator here is the same generator (sanitized for portability).

If you want to see how it reads at scale, browse a week of it. Then come back and fork the structure for your own project.

## License

- Code: MIT (see repo root LICENSE)
- Prose, framework, and example content: CC BY 4.0

Attribution: "days-chronicle pattern · iBitLabs" with a link to this repo or to https://www.ibitlabs.com/days.

## Status

Extracted 2026-04-23 from the iBitLabs private main repo. Reference implementation at Day 17 in production. This extraction is the first standalone release. Issues welcome.
