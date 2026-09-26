# Pain Radar

A free daily report of real problems people complained about in the last
24-48 hours — filtered for ones a solo person could plausibly build a rough
version of in two weekends, where someone's already paying for a bad
solution.

$0 budget. Free API tiers only, no card anywhere. Built for a beginner
coder to run and tune without touching Python.

## Status (2026-09-24)

| Stage | State |
|---|---|
| 1 — collect (~30 free sources) | ✅ working. Reddit RSS evaluated and REJECTED (429s even at 15s spacing, 0-16% yield). cursor + openai forums tried and removed (0 real problems, all vendor bug reports). Added fly.io / coda / glide forums (small, unproven). |
| 2 — filter (pain + money keyword scoring) | ✅ working. Keyword pass rate is NOT the same as real problems — judge sources by triage yield. |
| 3 — AI synthesis (Gemini clustering/scoring) | ✅ working. Pinned `gemini-3.5-flash-lite`. Nondeterministic: same post scored 18.0 then 14.0. |
| 3b — rejected-clusters log + per-post triage | ✅ new. `reports/rejected/DATE.md`: clusters cut after clustering (with reason) + a temp-0 Gemini verdict per shortlisted post and a per-source yield table. Best-effort, never breaks the report. Also on the run summary page. |
| 3c — triage gate + gigs | ✅ new 2026-09-26. Clusters may only cite posts triaged `real_problem`. Posts triaged `paid_gig` (someone hiring a freelancer) get a **Gigs** section in the report + Telegram — work to take, not ideas; not scored. Both depend on the best-effort triage call: if it fails, no gating and no gigs that day. |
| 4 — GitHub Actions cron | ✅ working. Gate is now idempotent ("no `reports/<UTC date>.md` yet") with retry crons — GitHub delivers `schedule` hours late. |
| Telegram delivery | ✅ working (was mis-pasted secrets, see below) |
| 5 — 2-week review | 📅 Thu 2026-10-08, `review.yml` → `reports/review-2026-10-08.md` + Telegram |

**Why ~1 idea/day:** sources are mostly help-desk forums; of ~34 shortlisted
posts Gemini finds ~1-6 real problems. The score bar is not the limiter.

## ✅ Resolved 2026-09-24 — Telegram on Actions

Cause: the GitHub secrets were wrong, not the code. `TG_TOKEN` was 55 chars
(the whole `TG_TOKEN=<token>` line pasted, prefix included) and `TG_CHAT_ID`
held a 46-char non-numeric value. Correct shapes: token 46 chars
(`<10 digits>:<35 chars>`), chat id 10 digits. Re-pasted values only (no
`NAME=` prefix, no quotes) and the message delivered. If it ever 404s again,
suspect the secrets first; add a temporary step printing `${#TG_TOKEN}` and a
regex shape check (lengths/booleans only, never the value).

Also fixed 2026-09-24: the old "London hour == 07" gate skipped runs when
GitHub delivered the cron hours late (green run, no report). Gate is now
"no reports/<UTC date>.md yet" plus retry crons.

## 📅 Scheduled review — Thu 2026-10-08

`.github/workflows/review.yml` builds `reports/review-2026-10-08.md` (14-day
digest: ideas/day, source yield from Gemini triage, checklist) and sends a
Telegram summary. Manual: `python3 run.py review [--since D --until D] [--dry-run]`.
Changes to sources/thresholds should cite a number from that digest.

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
- Gemini free tier genuinely rate-limits/503s under load sometimes —
  `run.py report` retries automatically with backoff (~1 min budget)
  before giving up. Pin `synthesis.model` in `config/scoring.yml` to a
  named, non-preview model (not a `-latest` alias) - a floating alias
  silently repointed to a brand-new preview model with a 20-requests/DAY
  cap during this project's build, which looked exactly like a sustained
  outage until traced to the real cause.
- A hard-to-diagnose Gemini `400 Bad Request` happened once on GitHub
  Actions and never reproduced locally with similar-sized fresh data -
  likely a one-off. `radar/synthesize.py` now prints the real response
  body on any HTTP failure (previously only the useless generic urllib
  message), so if it recurs, the actual reason will be visible in the
  Action's log instead of another blind guess.
- **Telegram on GitHub Actions is currently broken** - see "Open issue"
  in Status above for the live troubleshooting state.

## Repo

Public at https://github.com/nickwai/pain-radar (needed for free GitHub
Actions minutes). Working copy: `/home/oc/projects/pain-radar`.
