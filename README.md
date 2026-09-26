# Pain Radar

A free daily report of real problems people complained about in the last
24-48 hours — filtered for ones a solo person could plausibly build a rough
version of in two weekends, where someone's already paying for a bad
solution. Also lists freelance gigs (people hiring) it spots on the way.

$0 budget. Free API tiers only, no card anywhere. Built for a beginner
coder to run and tune without touching Python.

## Status (2026-09-26)

| Stage | State |
|---|---|
| 1 — collect (39 sources) | ✅ 21 Discourse forums, 12 forum RSS feeds, HN (10 phrases + Ask HN), Lobsters, 4 Stack Exchange sites. ~620-660 raw posts/day. Reddit REJECTED (see below). |
| 1a — full-window coverage | ✅ 2026-09-26. Feeds only return their newest ~20-30 items, which on busy forums spanned minutes of the 48h lookback. Fixed per source type: Discourse pages `/latest.json` (`discourse.max_pages: 3`; n8n 30 → 50 posts); forum RSS switched to new-thread feeds (XenForo `?order=post_date`, phpBB `?mode=topics`, Invision paging via `page_url`/`max_pages`, `also_urls` to merge a reply feed). Span of 48h window, before → after: elitetrader 13.7→45h, bogleheads 0.2→18h, garagejournal 1.9→45h, watchuseek 0.6→9.7h, eurobricks 2.7→18.7h, hardwarezone 0.1→2.7h. The collect log prints each feed's span. |
| 1b — HN phrase match | ✅ 2026-09-26. Algolia matches loosely (~1% of hits contained the query phrase). One request per query now fetches the whole window (`hits_per_query: 1000`) and `phrase_match: true` keeps only real phrase hits. Queries reworded from measured 48h exact-hit counts; plus every Ask HN story (`ask_hn: true`). ~145 posts/48h. |
| 1c — owner/seller sources | ✅ 2026-09-26. Probed 45 seller/shop-owner communities; added dealerrefresh (car dealer ops), ninjatrader + tradovate (paying traders), bunpro (paid Japanese SRS), woocommerce (shop owners). Rejected: autogeekonline, toyark, cgccomics (hobby/sale chat), prestashop (spam), squarespace (CSS help). No usable fashion or toy seller source exists with a free feed. |
| 2 — filter (pain + money keyword scoring) | ✅ working. Industry-keyword study 2026-09-26 (914 posts, 58 phrases): no keywords added — every lift was sale listings, news or hobby chat. Judge sources by triage yield, not keyword pass rate. |
| 2a — hiring pass | ✅ 2026-09-26. `hiring_regex` / `hiring_exclude` (keywords.yml) send up to `max_gigs` (6) hiring posts to the AI, bypassing `exclude` and scoring. |
| 2b — always_channels | ✅ 2026-09-26. Owner communities in `scoring.yml always_channels` skip the pain/money score test (0/22 dealerrefresh, 0/12 ninjatrader passed it); up to `max_always` (10), round-robin per channel. Both 2a and 2b go on top of `shortlist.total`, never displacing posts. |
| 3 — AI synthesis (Gemini clustering/scoring) | ✅ working. Pinned `gemini-3.5-flash-lite`. Nondeterministic: same post scored 18.0 then 14.0; the Baserow freeze post got ease 5 (reported) in one 09-26 run and ease 2 ("not buildable") in another; a real problem can be clustered one run and skipped the next. |
| 3a — per-post triage | ✅ Second Gemini call (temp 0) gives every shortlisted post a verdict: `real_problem`, `paid_gig`, `help_question`, `product_bug_report`, `out_of_industry`, `not_a_problem`. Best-effort: if it fails, the report still runs, without gating or gigs. |
| 3a2 — second clustering pass | ✅ 2026-09-26. Posts triage marked `real_problem` that the first clustering call left out are re-clustered in one extra call (same prompt, same judgement), only when there are any. Ideas from it say *Found on the second clustering pass* in the report. `synthesis.second_pass: false` turns it off. First live run (09-26): 7 real_problem, first pass used 1, second pass got 6 → 3 clusters, all cut (1 already reported, 2 not buildable); 3 posts skipped by both passes. Judgement was not lenient. |
| 3a3 — idea sanity checks | ✅ 2026-09-26. Clustering prompt now asks per idea: `existing_solutions` (tools or the platform's own built-in feature already solving it — shown as **Already exists** in report + Telegram, lowers scores, not a hard cut) and `target_user_has_access` + `access_reason` (can the person actually get the API/data/account access a first version needs — if `false` the idea is cut). Live check: the Tradovate lock-out idea now comes back access=false, money 1, and is cut. Existing-solution names are only as good as the model's knowledge (it said "third-party risk management desktop apps", not TradeReign) — verify before building. |
| 3b — triage gate | ✅ 2026-09-26. Ideas may only cite posts triaged `real_problem` (a help question leaked into the 09-26 report before this). |
| 3c — gigs | ✅ 2026-09-26. `paid_gig` posts get a **Gigs** section in the report + Telegram, unscored. |
| 3d — cross-day dedupe | ✅ 2026-09-26 (`radar/history.py`). Reads links from the last `dedupe_days` (30) of `reports/DATE.md`. An idea is dropped only if ALL its posts were reported before; gigs are dropped if already shown. Discourse URLs match on topic id. No state file. |
| 3e — rejected log | ✅ `reports/rejected/DATE.md`: ideas cut after clustering (with reason), **real problems that did not become ideas** (triage said `real_problem`, neither clustering pass used them — added 2026-09-26), gigs not repeated, and every post's verdict with a per-source yield table. |
| 4 — GitHub Actions cron | ✅ working. Gate is idempotent ("no `reports/<UTC date>.md` yet") with retry crons — GitHub delivers `schedule` hours late. A manual run (Actions → Run workflow) always runs and overwrites today's report. |
| Telegram delivery | ✅ working |
| 5 — 2-week review | 📅 Thu 2026-10-08, `review.yml` → `reports/review-2026-10-08.md` + Telegram |

**Why ~1 idea/day:** most sources are help-desk forums; of ~30-40
shortlisted posts Gemini finds ~1-6 real problems, and clustering often
turns only some of those into ideas. The score bar is not the limiter.

**First idea from one of your own industries:** 2026-09-26, trading — a
tradovate feature request (daily trade-count lock-out for prop traders).
It was the one idea that held up across all four 09-26 runs (score 21.0).
Checked the same day — **verdict: weak, don't build as a product.** Prop-firm
accounts get no Tradovate API (forum consensus; personal API needs a $1,000
funded account + $25/mo, market data extra), so the report's "API script"
first step is impossible for the people asking. The only route is browser
automation, needing each prop firm's approval. Already covered: Tradovate's
own daily-loss auto-lock + Manual Lockout (on Tradovate Prop since
2026-06-24), TradeReign (paid, advertises max-trades-per-day lockouts), and
the free MIT `trevislee/tradovate-lockout` (loss limits only). Only
recurring scheduled lockouts looked uncovered.

## 📅 Scheduled review — Thu 2026-10-08

`.github/workflows/review.yml` builds `reports/review-2026-10-08.md` (14-day
digest: ideas/day, source yield from Gemini triage, checklist) and sends a
Telegram summary. Manual: `python3 run.py review [--since D --until D] [--dry-run]`.
Changes to sources/thresholds should cite a number from that digest.

Open questions to settle there, with the data:

- **HN yield.** 0 real problems of 9 HN posts on the first run with the new
  queries. If still ~0, cut HN or its 9-post shortlist share.
- **dealerrefresh** is mostly vendors pitching to dealers (0/3 real on day
  one). Topics are right; posts are ads. Keep or drop on yield.
- **New sources** (ninjatrader, tradovate, bunpro, woocommerce): yield per
  source over two weeks.
- **Second clustering pass.** Count ideas marked *second pass* and how
  many were worth reading. If they're weak, set `second_pass: false`.
  Posts still listed under "Real problems that did not become ideas" were
  rejected twice.
- **Idea sanity checks (3a3).** Count ideas cut for access, and read the
  "Already exists" lines: are they specific and right, or vague? If the
  access check cuts good ideas, loosen the prompt wording.
- **Coverage gaps left:** hardwarezone still spans only ~2.7h (subforum
  feeds would help); styleforum ~7h (its new-thread feed is broken);
  purseblog 403 on every variant; fashion and toys have no seller-side
  source.

## What it does

Every morning on GitHub Actions (or by hand, see below):

1. **Collect** — pulls ~620-660 posts from 39 sources into `data/raw/DATE.json`.
2. **Filter** — scores every post on pain phrases + money phrases + real
   dollar amounts, cuts noise (sale listings, job ads, self-promo), keeps
   the top ~30-40 in `data/shortlist/DATE.json`. On top of that it adds
   hiring posts (up to 6) and posts from small owner communities (up to 10).
3. **Report** — two Gemini calls (three when needed). One gives each post a verdict (triage);
   the other clusters related posts into distinct problems, judges each
   against your filter (near your industries, buildable in two weekends,
   no team/licence/capital/network-effect blocker) and scores 1-5 on
   frequency / anger / money-evidence / ease-to-build. Real problems the
   clustering skipped get a second clustering call. Python then keeps
   only ideas backed by `real_problem` posts, drops ideas already reported
   in the last 30 days, applies the weights, the hard filter and the top-5
   cap. Writes `reports/DATE.md` (ideas + gigs), `reports/rejected/DATE.md`
   (everything that was cut and why) and sends the ideas + gigs to Telegram.

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

Instead: 21 Discourse forums, 12 XenForo/phpBB/Invision/bbPress RSS feeds,
HN Algolia, Lobsters, and 4 Stack Exchange sites — all free, no signup, no
key. Several were chosen because their users are **already paying** —
a monthly bill (Bubble, Make.com, Retool, Baserow, NocoDB, Shopify dev
forum, bunpro) or a trading platform (ninjatrader, tradovate) — the
strongest version of "money already being spent" this project's brief
asked for.

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
- `TG_TOKEN` / `TG_CHAT_ID` — optional; Telegram sends automatically when
  both are set.
- `REDDIT_*` — only needed if you re-enable Reddit in `config/sources.yml`.

## Running it

```bash
python3 run.py check              # ping every source, ~30s - find dead feeds
python3 run.py collect            # Stage 1 -> data/raw/DATE.json, ~2 min
python3 run.py filter --show 25   # Stage 2 -> data/shortlist/DATE.json
python3 run.py report             # Stage 3 -> reports/DATE.md + rejected/ + Telegram
python3 run.py report --dry-run   # same, but prints instead of writing/sending
python3 run.py review             # 14-day digest -> reports/review-DATE.md
```

Run them in order — each stage reads the previous stage's most recent
output file, not necessarily today's date (so a missed day doesn't break
the chain, it just works on stale data until you re-collect).

Forums throttle repeated hits: collect once a day, don't loop it. To test
the whole pipeline in the cloud, use Actions → "Daily Pain Radar report" →
Run workflow (it overwrites today's report and sends Telegram again).

## Tuning it yourself — no code, ever

Everything that decides what you see lives in three YAML files. Edit,
save, rerun — that's the whole workflow.

**`config/sources.yml`** — where it looks.
- Add a source: paste a line under `discourse.forums` (needs `/latest.json`)
  or `rss.feeds` (needs any RSS/Atom URL). Test first:
  `curl -s https://SITE/latest.json | head -c 200`. For forum RSS, prefer
  the new-thread feed (XenForo `?order=post_date`, phpBB `?mode=topics`),
  then check the span the collect log prints.
- Remove a source: delete its line. Nothing else changes.
- `lookback_hours: 48` controls how far back Stage 1 looks.
- `discourse.max_pages`, and per RSS feed `page_url` + `max_pages` /
  `also_urls` — how far busy feeds page back.
- `hackernews.queries` — exact phrases (with `phrase_match: true`);
  `ask_hn` pulls every Ask HN story.

**`config/keywords.yml`** — what counts as "pain" or "money" in Stage 2.
- `pain` / `money` — phrase lists, matched case-insensitively
- `money_regex` — real dollar-amount patterns (only count alongside a
  real money phrase, so a bare price tag in a for-sale listing can't win)
- `exclude` / `exclude_soft` — title phrases that kill a post outright
  (for-sale listings, job ads, self-promo, "rate my setup" threads)
- `hiring_regex` / `hiring_exclude` — what counts as someone hiring (a gig)
  vs someone selling their own services

**`config/scoring.yml`** — the weights, in two layers:
- `weights` / `group_multiplier` / `shortlist` — Stage 2's keyword-match
  scoring (which ~30-40 posts reach the AI). `shortlist.max_gigs`,
  `always_channels` and `max_always` control the extras added on top.
- `user_industries` — your industries. Edit this list any time; Gemini
  rejects anything outside it.
- `synthesis` — Stage 3's weights (`money_evidence` weighted highest, per
  the brief), `max_ideas` (default 5), `min_total_score` (raise it if the
  report feels padded, lower it if you're seeing "Nothing today" too
  often), `dedupe_days` (30; 0 = off), `triage_enabled`.

## Free-tier limits, and where this sits inside them

| Service | Free limit | This project's usage |
|---|---|---|
| Gemini (`gemini-3.5-flash-lite`, pinned) | ~1,500 requests/day | 2-3 per run (triage + clustering, + second pass when needed) |
| Groq (fallback, untested) | generous | 0 unless Gemini fails |
| HN Algolia | ~10k/hr soft | 11/run |
| Stack Exchange (no key) | 300/day/IP | ~4/run |
| Discourse / RSS forums | none published, but throttle on bursts | ~60/run, spaced with delays |

## Known rough edges

- `purseblog` 403s on every feed variant (Cloudflare) since 2026-09-26;
  `styleforum` occasionally times out. Both self-heal or stay skipped —
  a dead feed never breaks the run.
- Discourse's `/latest.json` returns no post body text; the collector also
  fetches `/latest.rss` (same pages) and joins them on topic ID to get real
  bodies. `community.fly.io` blocks its RSS, so it has titles only.
- Many forum RSS feeds carry only a short excerpt (hardwarezone median
  ~160 chars, trade2win ~100), which limits what the keyword filter can see.
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
  body on any HTTP failure, so if it recurs, the actual reason will be
  visible in the Action's log instead of another blind guess.

## Resolved issues

**2026-09-24 — Telegram on Actions.** Cause: the GitHub secrets were wrong,
not the code. `TG_TOKEN` was 55 chars (the whole `TG_TOKEN=<token>` line
pasted, prefix included) and `TG_CHAT_ID` held a 46-char non-numeric
value. Correct shapes: token 46 chars (`<10 digits>:<35 chars>`), chat id
10 digits. If it ever 404s again, suspect the secrets first; add a
temporary step printing `${#TG_TOKEN}` and a regex shape check
(lengths/booleans only, never the value).

**2026-09-24 — late crons.** The old "London hour == 07" gate skipped runs
when GitHub delivered the cron hours late (green run, no report). Gate is
now "no reports/<UTC date>.md yet" plus retry crons.

**2026-09-26 — same idea on several days.** Forums keep old topics on
`/latest` while they get replies; fixed by cross-day dedupe (3d).

## Repo

Public at https://github.com/nickwai/pain-radar (needed for free GitHub
Actions minutes). Working copy: `/home/oc/projects/pain-radar`.
