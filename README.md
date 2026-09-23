# Pain Radar

A free daily report of real problems people complained about in the last
24-48 hours — filtered for ones a solo person could plausibly build a rough
version of in two weekends, where someone's already paying for a bad
solution.

$0 budget. Free API tiers only, no card anywhere. Built for a beginner
coder to run and tune without touching Python.

## Status (2026-09-23)

| Stage | State |
|---|---|
| 1 — collect (28 free sources) | ✅ working |
| 2 — filter (pain + money keyword scoring) | ✅ working |
| 3 — AI synthesis (Gemini clustering/scoring) | ✅ code done, **not yet run successfully end-to-end** — blocked on a live Gemini free-tier capacity outage hit while building it (Google-side `503 high demand`, confirmed not a bug here: key valid, 2 different models both affected, schema-free requests also failed). Retries automatically; try `python3 run.py report --dry-run` any time. |
| 4 — GitHub Actions cron | ❌ not started |
| 5 — this README / tuning guide | ✅ this file |

## What it does

Every morning (once Stage 4 exists — for now, run by hand):

1. **Collect** — pulls ~500-600 posts from 28 sources into `data/raw/DATE.json`
2. **Filter** — scores every post on pain phrases + money phrases + real
   dollar amounts, cuts noise (sale listings, job ads, self-promo), keeps
   the top ~30-40 in `data/shortlist/DATE.json`
3. **Report** — sends the shortlist to Gemini in one call. It clusters
   related posts into distinct problems, judges each against your filter
   (near your industries, buildable in two weekends, no team/licence/
   capital/network-effect blocker), scores 1-5 on frequency / anger /
   money-evidence / ease-to-build. Python then applies the weights, the
   hard filter, and the top-5 cap — the model clusters and judges, the
   config decides what counts. Writes `reports/DATE.md`.

If nothing clears the bar, the report says **"Nothing today"** — never
padded to look busy, that was the whole point of the brief this was built
against.

## Why no Reddit

Reddit disabled self-serve API key creation platform-wide (their
"Responsible Builder Policy") partway through building this. Public
`.json` endpoints now 403; RSS technically still works but throttles to
roughly one request per 4 minutes per IP, unworkable for ~40 subreddits on
a daily cron. The Reddit collector code is still in `radar/collect.py`,
gated behind `reddit.enabled: false` in `config/sources.yml` — flip it on
if you ever get approved API access.

Instead: 15 Discourse forums, 10 XenForo/Invision RSS feeds, HN Algolia,
Lobsters, and 4 Stack Exchange sites — all free, no signup, no key. Several
were deliberately chosen because their users are **already paying a
monthly bill** (Bubble, Make.com, Retool, Baserow, NocoDB, Shopify dev
forum) — the strongest version of "money already being spent" this
project's brief asked for.

## Setup

```bash
cd /home/oc/projects/pain-radar
python3 -m pip install -r requirements.txt   # requests, PyYAML
cp .env.example .env
```

Edit `.env`:
- `GEMINI_API_KEY` — required for Stage 3. Free, no card:
  https://aistudio.google.com/apikey
- `GROQ_API_KEY` — optional fallback if Gemini fails/rate-limits.
  **Untested** — no key was available to verify this path; report an
  issue if it errors.
- `REDDIT_*` — only needed if you re-enable Reddit in `config/sources.yml`.

## Running it

```bash
python3 run.py check              # ping every source, ~30s - find dead feeds
python3 run.py collect            # Stage 1 -> data/raw/DATE.json, ~2-3 min
python3 run.py filter --show 25   # Stage 2 -> data/shortlist/DATE.json
python3 run.py report             # Stage 3 -> reports/DATE.md
python3 run.py report --dry-run   # same, but prints instead of writing
```

Run them in order — each stage reads the previous stage's most recent
output file, not necessarily today's date (so a missed day doesn't break
the chain, it just works on stale data until you re-collect).

## Tuning it yourself — no code, ever

Everything that decides what you see lives in three YAML files. Edit,
save, rerun — that's the whole workflow.

**`config/sources.yml`** — where it looks.
- Add a source: paste a line under `discourse.forums` (needs `/latest.json`)
  or `rss.feeds` (needs any RSS/Atom URL). Test first:
  `curl -s https://SITE/latest.json | head -c 200`
- Remove a source: delete its line. Nothing else changes.
- `lookback_hours: 48` controls how far back Stage 1 looks.

**`config/keywords.yml`** — what counts as "pain" or "money" in Stage 2.
- `pain` / `money` — phrase lists, matched case-insensitively
- `money_regex` — real dollar-amount patterns (only count alongside a
  real money phrase, so a bare price tag in a for-sale listing can't win)
- `exclude` / `exclude_soft` — title phrases that kill a post outright
  (for-sale listings, job ads, self-promo, "rate my setup" threads)

**`config/scoring.yml`** — the weights, in two layers:
- `weights` / `group_multiplier` / `shortlist` — Stage 2's keyword-match
  scoring (which ~30-40 posts reach the AI)
- `user_industries` — your industries. Edit this list any time; Gemini
  rejects anything outside it.
- `synthesis` — Stage 3's weights (`money_evidence` weighted highest, per
  the brief), `max_ideas` (default 5), `min_total_score` (raise it if the
  report feels padded, lower it if you're seeing "Nothing today" too
  often)

## Free-tier limits, and where this sits inside them

| Service | Free limit | This project's usage |
|---|---|---|
| Gemini (`gemini-flash-latest`) | ~1,500 requests/day | 1 per run (all posts, one call) |
| Groq (fallback, untested) | generous | 0 unless Gemini fails |
| HN Algolia | ~10k/hr soft | ~10/run |
| Stack Exchange (no key) | 300/day/IP | ~4/run |
| Discourse / RSS forums | none published, but throttle on bursts | ~30/run, spaced with delays |

Daily volume lands around 500-600 raw posts, well inside the ~30-50/day
range from the original brief once weekends/quiet nights are averaged in.

## Known rough edges

- `purseblog` and `styleforum` intermittently 403 (Cloudflare) — self-heals
  on the next run, not worth chasing.
- Discourse's `/latest.json` returns no post body text; the collector also
  fetches `/latest.rss` from the same forum and joins them on topic ID to
  get real bodies. If you add a Discourse forum and its filter results look
  thin, check this joined correctly.
- Gemini free tier genuinely rate-limits/503s under load sometimes (see
  Status above) — `run.py report` retries automatically with backoff
  (~1 min budget) before giving up.

## Repo

No remote configured yet — this exists only as local commits in
`/home/oc/projects/pain-radar`. Add one (`git remote add origin <url>`)
when you're ready to back it up off this machine.
