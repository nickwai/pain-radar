# Pain Radar

A free daily report of real problems people complained about in the last
24-48 hours — filtered for ones a solo person could plausibly build a rough
version of in two weekends, where someone's already paying for a bad
solution. Also lists freelance gigs (people hiring) it spots on the way.

$0 budget. Free API tiers only, no card anywhere. Built for a beginner
coder to run and tune without touching Python.

## Status (2026-09-28)

| Stage | State |
|---|---|
| 1 — collect (39 sources) | ✅ 21 Discourse forums, 12 forum RSS feeds, HN (10 phrases + Ask HN), Lobsters, 4 Stack Exchange sites. ~620-660 raw posts/day. Reddit REJECTED (see below). |
| 1a — full-window coverage | ✅ 2026-09-26. Feeds only return their newest ~20-30 items, which on busy forums spanned minutes of the 48h lookback. Fixed per source type: Discourse pages `/latest.json` (`discourse.max_pages: 3`; n8n 30 → 50 posts); forum RSS switched to new-thread feeds (XenForo `?order=post_date`, phpBB `?mode=topics`, Invision paging via `page_url`/`max_pages`, `also_urls` to merge a reply feed). Span of 48h window, before → after: elitetrader 13.7→45h, bogleheads 0.2→18h, garagejournal 1.9→45h, watchuseek 0.6→9.7h, eurobricks 2.7→18.7h, hardwarezone 0.1→2.7h. The collect log prints each feed's span. |
| 1b — HN phrase match | ✅ 2026-09-26. Algolia matches loosely (~1% of hits contained the query phrase). One request per query now fetches the whole window (`hits_per_query: 1000`) and `phrase_match: true` keeps only real phrase hits. Queries reworded from measured 48h exact-hit counts; plus every Ask HN story (`ask_hn: true`). ~145 posts/48h. |
| 1c — owner/seller sources | ✅ 2026-09-26. Probed 45 seller/shop-owner communities; added dealerrefresh (car dealer ops), ninjatrader + tradovate (paying traders), bunpro (paid Japanese SRS), woocommerce (shop owners). Rejected: autogeekonline, toyark, cgccomics (hobby/sale chat), prestashop (spam), squarespace (CSS help). No usable fashion or toy seller source exists with a free feed. |
| 2 — filter (pain + money keyword scoring) | ✅ working. Industry-keyword study 2026-09-26 (914 posts, 58 phrases): no keywords added — every lift was sale listings, news or hobby chat. Judge sources by triage yield, not keyword pass rate. |
| 2a — hiring pass | ✅ 2026-09-26. `hiring_regex` / `hiring_exclude` (keywords.yml) send up to `max_gigs` (6) hiring posts to the AI, bypassing `exclude` and scoring. |
| 2b — always_channels | ✅ 2026-09-26. Owner communities in `scoring.yml always_channels` skip the pain/money score test (0/22 dealerrefresh, 0/12 ninjatrader passed it); up to `max_always` (10), round-robin per channel. Both 2a and 2b go on top of `shortlist.total`, never displacing posts. |
| 3 — AI synthesis (Gemini clustering/scoring) | ✅ working. Pinned `gemini-3.5-flash-lite`. Nondeterministic: same post scored 18.0 then 14.0; the Baserow freeze post got ease 5 (reported) in one 09-26 run and ease 2 ("not buildable") in another; a real problem can be clustered one run and skipped the next. Main cause found 09-26: the clustering call set no temperature (model default); now `synthesis.temperature: 0` (see 3a3). Triage (already temp 0) still drifted: 4-7 real_problem in earlier 09-26 runs, 13 in the last, including help questions and showcases. |
| 3a — per-post triage | ✅ Second Gemini call (temp 0) gives every shortlisted post a verdict: `real_problem`, `paid_gig`, `help_question`, `product_bug_report`, `out_of_industry`, `not_a_problem`. Best-effort: if it fails, the report still runs, without gating or gigs. |
| 3a2 — second clustering pass | ✅ 2026-09-26. Posts triage marked `real_problem` that the first clustering call left out are re-clustered in one extra call (same prompt, same judgement), only when there are any. Ideas from it say *Found on the second clustering pass* in the report. `synthesis.second_pass: false` turns it off. First live run (09-26): 7 real_problem, first pass used 1, second pass got 6 → 3 clusters, all cut (1 already reported, 2 not buildable); 3 posts skipped by both passes. Judgement was not lenient. |
| 3a3 — idea sanity checks | ✅ 2026-09-26. Clustering prompt now asks per idea: `existing_solutions` (tools or the platform's own built-in feature already solving it — shown as **Already exists** in report + Telegram, lowers scores, not a hard cut) and `target_user_has_access` + `access_reason` (can the person actually get the API/data/account access a first version needs — if `false` the idea is cut). Live check: the Tradovate lock-out idea now comes back access=false, money 1, and is cut. The access reason is shown for kept ideas too (report + Telegram). Clustering now runs at `synthesis.temperature: 0` — before, no temperature was set and the same post flipped between runs; live check: a 34-post shortlist gave the identical cluster twice, but a 2-post test still varied (0/0/1 clusters), so it narrows the variation without removing it. The access answer itself is still unreliable (Shopify email-template idea: access=true in one run, false in another). Existing-solution names are only as good as the model's knowledge (it said "third-party risk management desktop apps", not TradeReign) — verify before building. |
| 3b — triage gate | ✅ 2026-09-26. Ideas may only cite posts triaged `real_problem` (a help question leaked into the 09-26 report before this). |
| 3c — gigs | ✅ 2026-09-26. `paid_gig` posts get a **Gigs** section in the report + Telegram, unscored. |
| 3d — cross-day dedupe | ✅ 2026-09-26 (`radar/history.py`). Reads links from the last `dedupe_days` (30) of `reports/DATE.md`. An idea is dropped only if ALL its posts were reported before; gigs are dropped if already shown. Discourse URLs match on topic id. No state file. |
| 3e — rejected log | ✅ `reports/rejected/DATE.md`: ideas cut after clustering (with reason), **real problems that did not become ideas** (triage said `real_problem`, neither clustering pass used them — added 2026-09-26), gigs not repeated, and every post's verdict with a per-source yield table. |
| 3f — money floor | ✅ 2026-09-28. `synthesis.min_money_evidence: 3` cuts any idea whose "Money already spent" score is below 3, before the total-score check. Reason: easy-to-build ideas with money 1 cleared `min_total_score` on ease alone (09-27 and 09-28 NinjaTrader drawing-tool ideas, both money 1 — nobody pays for a workaround). Of the 6 ideas reported 09-23→09-28, 3 would have been cut (money 2, 1, 1). Cut ideas go to the rejected log with the reason. Expect more "Nothing today" days. Set to 1 to turn off. |
| 4 — GitHub Actions cron | ✅ working. Gate is idempotent ("no `reports/<UTC date>.md` yet") with retry crons — GitHub delivers `schedule` hours late. A manual run (Actions → Run workflow) always runs and overwrites today's report. |
| Telegram delivery | ✅ working |
| 5 — 2-week review | ✅ Every second Thursday (`review.yml`, gate: last `reports/review-*.md` 13+ days old; next 2026-10-22, 2026-11-05). Digest: weekly ideas, competitor verdicts, weekly cuts by reason, pooled per day, source yield, checklist + Telegram. First one (2026-10-08): 8 ideas / 15 days, 0 survived a manual competitor check → 6-8 below. |
| 6 — pool + weekly ideas | ✅ 2026-10-08. `scoring.yml pool.enabled`: the daily run only triages and saves `real_problem` posts to `data/pool/DATE.json` (committed by CI); daily report + Telegram = pool count + gigs. `weekly.yml` (Mondays) runs `python3 run.py weekly`: clusters the last `pool.days` (14) of the pool at once (one copy per topic) → `reports/week-DATE.md` + `reports/rejected/week-DATE.md` + Telegram. Repeat pains across days now add up to one cluster instead of dying alone. `pool.enabled: false` = old daily ideas. |
| 7 — competitor check | ✅ 2026-10-08 (`radar/competitors.py`). Ideas that clear the bar get 3 search queries (Gemini) → HN Show HN + GitHub repo search → Gemini verdict `crowded` / `partial` / `open`, citing results by id. `crowded` is cut (`competitor_check.cut_verdicts`). Live test: the 10-04 n8n silent-failure and 09-26 Tradovate lock-out ideas both come back crowded with real links. Gemini Google Search grounding was the plan, but the free tier gives it 0 quota (429 on every model) and DuckDuckGo blocks scripts — so paid SaaS that never posted on HN can be missed; names from model memory are marked *unverified*. |
| 8 — source cuts | ✅ 2026-10-08, from review yield: bogleheads (4/38, personal investing advice), woocommerce (0/6), HN "too expensive" (0/20), HN "willing to pay" (0/11). |

**Why ~1 idea/day:** most sources are help-desk forums; of ~30-40
shortlisted posts Gemini finds ~1-6 real problems, and clustering often
turns only some of those into ideas. The total-score bar is not the limiter;
since 09-28 the money floor (3f) is, on purpose — an empty day beats an idea
nobody would pay for. Next lever (10-08 review): sources where people already
pay (paid-software reviews, hiring/freelance posts, "switched from X over
price" threads) rather than free feature-request forums.
**2026-10-08 — pool backfill showed triage was too loose.** `tools/backfill_pool.py`
re-fetched the bodies of the 09-29→10-06 `real_problem` posts (from the
rejected logs) and re-triaged them with today's prompt (self_promo filter,
full text): only 6 of 38 stayed real — 14 were sellers/promo, 9 not a problem,
7 help questions. The pool starts with those 7 posts.

**2026-10-04 trial (review ~2026-10-18):** a source study
(`docs/source-study-2026-10-04.md`) found app-store/review-site complaints
are vendor-only, while trade business sub-forums are full of owners' real
problems. Added industry "trades and field-service business operations"
plus `lawnsite-bizops` and `contractortalk-biz` as always_channels (~6
posts per 48h). Judge by: real_problem count from those two channels in the
rejected log, and whether any idea survives a competitor check (crowded
market: Jobber, Housecall Pro, LMN).

**2026-10-07 — 6 feeds were never live in CI.** GitHub Actions' log showed
watchuseek, lawnsite-bizops, contractortalk-biz (HTTP 409, one forum network)
and eurobricks, chinese-forums, purseblog (403) failing on EVERY run since
09-23, while all but purseblog return 200 from the home PC. A probe run (3
User-Agents incl. a browser and Feedly) got the same 403/409 → IP block, not
UA. Fix: those 5 feeds carry `fetch: local` in `config/sources.yml`; the home
PC runs `tools/push_local_feeds.sh` (systemd user timer
`painradar-local-feeds`, 05:40 + 17:40 London, Persistent) →
`python3 run.py collect-local` → commits `data/local/latest.json`; the
Actions collect skips those feeds and merges that file (posts still filtered
by the 48h lookback). The rejected log ends with
`**Local-fetch feeds (home PC):** ok / STALE / MISSING …` so a PC that was
off shows up. purseblog is 403 everywhere — left as is. Log on the PC:
`data/raw/local_feeds.log` (gitignored). ⚠️ The 10-04 source study and the
09-26 industry-keyword study were measured from the PC, so they included
sources the daily report never saw.

**First idea from one of your own industries:** 2026-09-26, trading — a
tradovate feature request (daily trade-count lock-out for prop traders).
It was the one idea that held up across all five 09-26 runs (score 21.0) —
including the run after the access check was added, where it passed with an
incorrect "Already exists" line and an API first step, which led to the
temperature-0 fix.
Checked the same day — **verdict: weak, don't build as a product.** Prop-firm
accounts get no Tradovate API (forum consensus; personal API needs a $1,000
funded account + $25/mo, market data extra), so the report's "API script"
first step is impossible for the people asking. The only route is browser
automation, needing each prop firm's approval. Already covered: Tradovate's
own daily-loss auto-lock + Manual Lockout (on Tradovate Prop since
2026-06-24), TradeReign (paid, advertises max-trades-per-day lockouts), and
the free MIT `trevislee/tradovate-lockout` (loss limits only). Only
recurring scheduled lockouts looked uncovered.

## 📅 Scheduled review — every second Thursday

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
  "Already exists" and "Access check" lines: are they specific and right,
  or vague? If the access check cuts good ideas, loosen the prompt wording.
- **Stability after temperature 0.** Do the same posts still flip between
  days (cut one day, reported the next)? If yes, add voting: cluster 2-3
  times and keep only ideas every run agrees on (+2-3 Gemini requests/day).
- **Triage drift.** real_problem count per day and how many are really help
  questions/showcases. If triage stays loose, the second pass and the
  "did not become ideas" list fill with noise.
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
  often), `min_money_evidence` (3; drops ideas nobody already pays to
  solve, 1 = off), `dedupe_days` (30; 0 = off), `triage_enabled`.

## Free-tier limits, and where this sits inside them

| Service | Free limit | This project's usage |
|---|---|---|
| Gemini (`gemini-3.5-flash-lite`, pinned) | ~1,500 requests/day | 2-3 per run (triage + clustering, + second pass when needed) |
| Groq (fallback, not configured) | generous | 0 — no `GROQ_API_KEY` secret on Actions, so a Gemini failure fails the run (decided 09-28: retry crons are enough) |
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
  before giving up. On 2026-09-28 three runs failed on sustained 503
  "high demand" and a run at 19:12 succeeded; the retry crons /
  a manual re-run are the recovery path (no Groq fallback). Pin `synthesis.model` in `config/scoring.yml` to a
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

**2026-10-04 — an ad became the top idea.** The 10-04 report's idea (score
26, money 5, "no-code workflows fail silently") came from an n8n post
selling the poster's own tool (matrixverify.dev); its "$2,500–8,000 per
failure" figures were sales copy. The pitch sat at the END of the post,
past the 600-char cut, so the AI never saw it. Fix: the AI now gets head
(450) + tail (200) of each long post, a `[promo signals: ...]` line from a
regex run on the full text (`PROMO_RE` in `radar/synthesize.py`), and a new
triage verdict `self_promo`, which `gate_by_triage` drops like any non-
`real_problem`. Live test: the Matrix post → `self_promo`; help questions
with "I built"/"I created" stayed `help_question`. Side effect: HA/n8n
showcase posts now read `self_promo` instead of `not_a_problem` in the
triage log. Competitors for that idea (all existing): watchflow.io,
NotiLens, FlowGuard, Pulse, Matrix, Healthchecks.io/Cronitor.
Same day, widened: a competitor check of all 4 ideas reported so far found
0 worth building, and 3 of the 4 source posts were sellers - the ad above,
a "how I fixed it" tip post (10-01, HTTP 200 on failure) and a consultant
fishing for clients (10-01, Zoho Books UK). `self_promo` now also covers
lead-gen posts and solved-problem tip posts, with extra regex signals
("happy to share", "teams I speak to", "the fix is", "DM me"). Live test,
16 posts: all 3 seller posts → `self_promo`, the genuine 09-29 Gmail agency
post stayed `real_problem`, 6/6 help questions unchanged, 5/6 real problems
unchanged - the 6th was an ad ("Free 4-minute security check") that old
triage had wrongly called real.

## Repo

Public at https://github.com/nickwai/pain-radar (needed for free GitHub
Actions minutes). Working copy: `/home/oc/projects/pain-radar`.
