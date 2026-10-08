#!/usr/bin/env python3
"""Pain Radar - daily report of real problems people are complaining about.

Usage:
    python3 run.py check       # Verify Reddit credentials
    python3 run.py collect     # Stage 1: fetch raw posts -> data/raw/DATE.json
    python3 run.py filter      # Stage 2: shortlist -> data/shortlist/DATE.json
    python3 run.py report      # Stage 3: triage -> data/pool/ (+ reports/DATE.md)
    python3 run.py weekly      # Stage 4: cluster the pool -> reports/week-DATE.md
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def load_env() -> None:
    """Read a local .env file if present. GitHub Actions supplies real env vars."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def today() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def cmd_check(_args: argparse.Namespace) -> int:
    """Ping every configured source once. Fast way to find a dead feed."""
    import requests
    import yaml

    UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/125.0.0.0 Safari/537.36")
    cfg = yaml.safe_load((ROOT / "config" / "sources.yml").read_text(encoding="utf-8"))

    targets: list[tuple[str, str]] = []
    for forum in cfg.get("discourse", {}).get("forums", []):
        targets.append((forum["url"].replace("https://", ""),
                        forum["url"].rstrip("/") + "/latest.json"))
    for feed in cfg.get("rss", {}).get("feeds", []):
        targets.append((feed.get("name", feed["url"]), feed["url"]))
    for site in cfg.get("stackexchange", {}).get("sites", []):
        targets.append((f"SE:{site}",
                        f"https://api.stackexchange.com/2.3/questions?site={site}&pagesize=1"))
    targets.append(("lobste.rs", "https://lobste.rs/newest.json"))
    targets.append(("HN algolia",
                    "https://hn.algolia.com/api/v1/search_by_date?query=test&hitsPerPage=1"))

    bad = 0
    for name, url in targets:
        try:
            resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
            items = resp.text.count("<item>") or resp.text.count("<entry>")
            if not items and "json" in resp.headers.get("content-type", ""):
                try:
                    data = resp.json()
                    for key in ("hits", "items", "topics"):
                        if isinstance(data, dict) and key in data:
                            items = len(data[key]); break
                    else:
                        if isinstance(data, list):
                            items = len(data)
                        elif isinstance(data, dict):
                            items = len(data.get("topic_list", {}).get("topics", []))
                except ValueError:
                    items = 0
            flag = "ok  " if resp.status_code == 200 and items else "DEAD"
            bad += flag == "DEAD"
            print(f"  {flag}  {name:<32} HTTP {resp.status_code}  items~{items}")
        except Exception as exc:  # noqa: BLE001
            bad += 1
            print(f"  DEAD  {name:<32} {type(exc).__name__}")
        time.sleep(0.5)

    print(f"\n{len(targets) - bad}/{len(targets)} sources alive")
    if bad:
        print("Dead ones are skipped automatically at collect time.")
        print("If one stays dead for days, delete its line from config/sources.yml.")
    return 0


def cmd_filter(args: argparse.Namespace) -> int:
    from radar.filter import load_configs, preview, shortlist

    raw_dir = ROOT / "data" / "raw"
    files = sorted(raw_dir.glob("*.json"))
    if not files:
        print("No raw data. Run: python3 run.py collect")
        return 1
    raw_path = files[-1]
    posts = json.loads(raw_path.read_text(encoding="utf-8"))
    print(f"Filtering {raw_path.name} ({len(posts)} posts)\n")

    keywords, scoring = load_configs(
        str(ROOT / "config" / "keywords.yml"),
        str(ROOT / "config" / "scoring.yml"))
    picked, stats = shortlist(posts, keywords, scoring)

    if not picked:
        print("\nNothing survived. Loosen min_score in config/scoring.yml.")
        return 1

    print("\nby industry:", dict(sorted(stats["per_group"].items())))
    preview(picked, limit=args.show)

    out_path = ROOT / "data" / "shortlist" / f"{raw_path.stem}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(picked, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(f"\nWrote {len(picked)} posts -> {out_path.relative_to(ROOT)}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    import yaml
    from radar.synthesize import synthesize, triage_posts
    from radar.history import drop_seen_gigs, reported_urls
    from radar.report import (gigs_from_triage, render, render_orphans,
                              render_rejected, render_triage)

    shortlist_dir = ROOT / "data" / "shortlist"
    files = sorted(shortlist_dir.glob("*.json"))
    if not files:
        print("No shortlist. Run: python3 run.py collect && python3 run.py filter")
        return 1
    shortlist_path = files[-1]
    posts = json.loads(shortlist_path.read_text(encoding="utf-8"))
    print(f"Synthesizing {shortlist_path.name} ({len(posts)} posts)\n")

    config = yaml.safe_load((ROOT / "config" / "scoring.yml").read_text(encoding="utf-8"))
    # IMPROVEMENT [2026-09-24]: collect clusters Gemini produced but the
    # filters cut, so they can be reviewed (reports/rejected/DATE.md).
    rejected: list[dict] = []
    # Best-effort per-post verdicts (never raises; [] on failure -> no gating,
    # section omitted). Run first so non-real_problem posts can't reach the report.
    triage = triage_posts(posts, config)
    date = shortlist_path.stem
    seen = reported_urls(ROOT / "reports", before=date,
                         days=config["synthesis"].get("dedupe_days", 30))
    if (config.get("pool") or {}).get("enabled"):
        return _report_pool_day(args, posts, config, triage, date, seen)
    ideas = synthesize(posts, config, rejected=rejected, triage=triage, seen=seen)

    posts_by_id = {p["id"]: p for p in posts}
    gigs, old_gigs = drop_seen_gigs(gigs_from_triage(triage), posts_by_id, seen)
    if old_gigs:
        print(f"  dropped {len(old_gigs)} gigs already in an earlier report")
    report_md = render(ideas, posts_by_id, config, date=date, gigs=gigs)
    rejected_md = render_rejected(rejected, posts_by_id, config, date=date)
    rejected_md += render_orphans(triage, ideas + rejected, posts_by_id)
    rejected_md += render_triage(triage, posts_by_id)
    # ADDED 2026-10-07: say whether the home-PC feeds made it into this run.
    from radar.collect import local_feeds_status
    rejected_md += f"\n**Local-fetch feeds (home PC):** {local_feeds_status()[1]}\n"
    if old_gigs:
        rejected_md += "\n**Gigs not shown again (already reported):**\n\n" + "".join(
            f"- {posts_by_id[g['id']]['title']} — {posts_by_id[g['id']]['url']}\n"
            for g in old_gigs)

    print("\n" + "=" * 60)
    print(report_md)

    # Telegram: sends automatically if credentials are present in .env,
    # same as Groq's fallback pattern - opt in by adding the key, no flag
    # needed. --dry-run and --no-telegram both skip it; --dry-run also
    # skips the file write below, so nothing has any side effect at all.
    if not args.dry_run and not args.no_telegram:
        tg_token = os.environ.get("TG_TOKEN")
        tg_chat_id = os.environ.get("TG_CHAT_ID")
        if tg_token and tg_chat_id:
            from radar.telegram import format_message, send

            tg_text = format_message(ideas, posts_by_id, date, gigs=gigs)
            delivered, detail = send(tg_text, tg_token, tg_chat_id)
            print(f"\n[telegram] {'sent' if delivered else 'FAILED'}: {detail}")
        else:
            print("\n[telegram] skipped - TG_TOKEN/TG_CHAT_ID not set in .env")

    if args.dry_run:
        print("(--dry-run: not writing to reports/)")
        return 0

    out_path = ROOT / "reports" / f"{date}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_md, encoding="utf-8")
    print(f"\nWrote report -> {out_path.relative_to(ROOT)}")
    rej_path = ROOT / "reports" / "rejected" / f"{date}.md"
    rej_path.parent.mkdir(parents=True, exist_ok=True)
    rej_path.write_text(rejected_md, encoding="utf-8")
    print(f"Wrote rejected clusters ({len(rejected)}) -> {rej_path.relative_to(ROOT)}")
    return 0


def next_weekly_date(date: str, weekday: int) -> str:
    """The weekly run's date on/after `date` (weekday: Monday=0)."""
    d = dt.date.fromisoformat(date)
    return (d + dt.timedelta(days=(weekday - d.weekday()) % 7)).isoformat()


def _send_telegram(text: str, args: argparse.Namespace) -> None:
    if args.dry_run or args.no_telegram:
        return
    tg_token, tg_chat = os.environ.get("TG_TOKEN"), os.environ.get("TG_CHAT_ID")
    if not (tg_token and tg_chat):
        print("\n[telegram] skipped - TG_TOKEN/TG_CHAT_ID not set in .env")
        return
    from radar.telegram import send
    ok, detail = send(text, tg_token, tg_chat)
    print(f"\n[telegram] {'sent' if ok else 'FAILED'}: {detail}")


def _report_pool_day(args, posts, config, triage, date, seen) -> int:
    """ADDED 2026-10-08 (pool.enabled): no clustering today. Save the day's
    real_problem posts to data/pool/DATE.json; `run.py weekly` clusters the
    window. The daily report + Telegram carry the pool count and gigs."""
    from radar.collect import local_feeds_status
    from radar.history import drop_seen_gigs
    from radar.pool import load_window, save_day
    from radar.report import gigs_from_triage, render_daily_pool, render_triage
    from radar.telegram import format_daily_pool

    pool_cfg = config["pool"]
    pool_dir = ROOT / "data" / "pool"
    posts_by_id = {p["id"]: p for p in posts}
    pooled = [] if args.dry_run else save_day(pool_dir, date, posts, triage)
    if args.dry_run:  # show what would be pooled, write nothing
        pooled = [{**posts_by_id[r["id"]], "triage_reason": r["reason"]}
                  for r in triage if r["verdict"] == "real_problem"]
    pool_size = len(load_window(pool_dir, date, pool_cfg.get("days", 14)))
    nxt = next_weekly_date(date, pool_cfg.get("weekday", 0))
    gigs, old_gigs = drop_seen_gigs(gigs_from_triage(triage), posts_by_id, seen)
    report_md = render_daily_pool(date, pooled, pool_size, pool_cfg.get("days", 14),
                                  nxt, gigs, posts_by_id, bool(triage))
    rejected_md = (f"# Triage — {date}\n\nPool mode: no clustering today; "
                   f"real_problem posts went to data/pool/{date}.json.\n")
    rejected_md += render_triage(triage, posts_by_id)
    rejected_md += f"\n**Local-fetch feeds (home PC):** {local_feeds_status()[1]}\n"
    if old_gigs:
        rejected_md += "\n**Gigs not shown again (already reported):**\n\n" + "".join(
            f"- {posts_by_id[g['id']]['title']} — {posts_by_id[g['id']]['url']}\n"
            for g in old_gigs)
    print("\n" + "=" * 60)
    print(report_md)
    _send_telegram(format_daily_pool(date, pooled, pool_size, nxt, gigs, posts_by_id,
                                     bool(triage)), args)
    if args.dry_run:
        print("(--dry-run: not writing to reports/ or data/pool/)")
        return 0
    (ROOT / "reports" / f"{date}.md").write_text(report_md, encoding="utf-8")
    rej_path = ROOT / "reports" / "rejected" / f"{date}.md"
    rej_path.parent.mkdir(parents=True, exist_ok=True)
    rej_path.write_text(rejected_md, encoding="utf-8")
    print(f"\nPooled {len(pooled)} -> data/pool/{date}.json; wrote reports/{date}.md")
    return 0


def cmd_weekly(args: argparse.Namespace) -> int:
    """ADDED 2026-10-08: cluster every pooled real problem of the last
    pool.days days at once, competitor-check what clears the bar, write
    reports/week-DATE.md + reports/rejected/week-DATE.md, send Telegram."""
    import yaml
    from radar.competitors import check
    from radar.history import reported_urls
    from radar.pool import load_window
    from radar.report import render, render_orphans, render_rejected
    from radar.synthesize import synthesize
    from radar.telegram import format_message

    config = yaml.safe_load((ROOT / "config" / "scoring.yml").read_text(encoding="utf-8"))
    days = (config.get("pool") or {}).get("days", 14)
    until = args.until or today()
    since = (dt.date.fromisoformat(until) - dt.timedelta(days=days - 1)).isoformat()
    period = f"{since} → {until}"
    posts = load_window(ROOT / "data" / "pool", until, days)
    pooled_days = len({p.get("pooled_on") for p in posts})
    intro = (f"Clustered {len(posts)} real problems pooled on {pooled_days} "
             f"day{'s' if pooled_days != 1 else ''}.")
    print(f"Weekly {period}: {len(posts)} pooled posts\n")

    # Every pooled post is already triaged real_problem: hand that verdict on
    # so the triage gate passes them and the second pass re-clusters orphans.
    triage = [{"id": p["id"], "verdict": "real_problem", "reason": p.get("triage_reason", "")}
              for p in posts]
    rejected: list[dict] = []
    seen = reported_urls(ROOT / "reports", before=until,
                         days=config["synthesis"].get("dedupe_days", 30))
    ideas = synthesize(posts, config, rejected=rejected, triage=triage, seen=seen) if posts else []
    ideas = check(ideas, config, rejected=rejected)

    posts_by_id = {p["id"]: p for p in posts}
    report_md = render(ideas, posts_by_id, config, date=until, period=period, intro=intro)
    rejected_md = render_rejected(rejected, posts_by_id, config, date=f"week {period}")
    rejected_md += render_orphans(triage, ideas + rejected, posts_by_id)
    print("\n" + "=" * 60)
    print(report_md)
    _send_telegram(format_message(ideas, posts_by_id, until, period=period, intro=intro), args)
    if args.dry_run:
        print("(--dry-run: not writing to reports/)")
        return 0
    (ROOT / "reports" / f"week-{until}.md").write_text(report_md, encoding="utf-8")
    rej_path = ROOT / "reports" / "rejected" / f"week-{until}.md"
    rej_path.parent.mkdir(parents=True, exist_ok=True)
    rej_path.write_text(rejected_md, encoding="utf-8")
    print(f"\nWrote reports/week-{until}.md and {rej_path.relative_to(ROOT)}")
    return 0


# Fixed test ideas for `check-competitors`. Expected verdicts come from the
# manual checks of 2026-09-26 (Tradovate) and 2026-10-04 (n8n): both crowded.
# The lawn-care one is info only (expected None): it was meant as a "not
# crowded" control, but the judge rightly names Jobber/ServiceTitan mobile
# timesheets - there is no known-open idea to assert against.
COMPETITOR_TEST_IDEAS = [
    ("crowded", {"problem_one_line": "No-code automation workflows (n8n, Make) fail silently "
                 "on invalid data states with no alert",
                 "who_has_it": "automation agency running client workflows in n8n/Make",
                 "existing_solutions": "n8n error workflow"}),
    ("crowded", {"problem_one_line": "Prop-firm futures traders on Tradovate need an automatic "
                 "scheduled lockout after N trades per day",
                 "who_has_it": "prop-firm futures trader on Tradovate",
                 "existing_solutions": "none known"}),
    (None, {"problem_one_line": "Lawn care business owners re-type crew timesheets "
                     "from paper into payroll every week",
                     "who_has_it": "owner of a 3-8 crew lawn care business",
                     "existing_solutions": "none given"}),
]


def cmd_check_competitors(_args: argparse.Namespace) -> int:
    """ADDED 2026-10-08: run radar/competitors.py on COMPETITOR_TEST_IDEAS.
    Prints only - no report, no Telegram. Exit 1 if a verdict is off."""
    import yaml
    from radar.competitors import check
    from radar.report import render_competitors

    config = yaml.safe_load((ROOT / "config" / "scoring.yml").read_text(encoding="utf-8"))
    ideas = [dict(i) for _, i in COMPETITOR_TEST_IDEAS]
    check(ideas, config)
    bad = 0
    for (expected, _), idea in zip(COMPETITOR_TEST_IDEAS, ideas):
        got = idea["competitor_check"]["verdict"]
        ok = got != "not run" and (expected is None or got == expected)
        bad += not ok
        tag = ("INFO" if ok else "FAIL") if expected is None else ("PASS" if ok else "FAIL")
        print(f"\n{tag}  expected {expected or 'any'}, got {got}: "
              f"{idea['problem_one_line'][:70]}")
        print("\n".join(render_competitors(idea["competitor_check"])))
    print(f"\n{len(ideas) - bad}/{len(ideas)} verdicts as expected")
    return 1 if bad else 0


def cmd_review(args: argparse.Namespace) -> int:
    """Two-week review digest -> reports/review-UNTIL.md (+ Telegram)."""
    import datetime as dt
    from radar.review import build

    until = args.until or today()
    since = args.since or (dt.date.fromisoformat(until) - dt.timedelta(days=14)).isoformat()
    full, short = build(ROOT / "reports", since, until)
    print(full)
    if args.dry_run:
        return 0
    out = ROOT / "reports" / f"review-{until}.md"
    out.write_text(full, encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)}")
    tg_token, tg_chat = os.environ.get("TG_TOKEN"), os.environ.get("TG_CHAT_ID")
    if tg_token and tg_chat:
        from radar.telegram import send
        ok, detail = send(short, tg_token, tg_chat)
        print(f"[telegram] {'sent' if ok else 'FAILED'}: {detail}")
    return 0


def cmd_collect(_args: argparse.Namespace) -> int:
    from radar.collect import collect

    posts = collect(str(ROOT / "config" / "sources.yml"))
    out_path = ROOT / "data" / "raw" / f"{today()}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(posts, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(posts)} posts -> {out_path.relative_to(ROOT)}")
    if not posts:
        print("WARNING: zero posts collected. Check the errors above.")
        return 1
    return 0


def cmd_collect_local(_args: argparse.Namespace) -> int:
    """ADDED 2026-10-07: home-PC fetch of feeds that block GitHub Actions
    (`fetch: local` in sources.yml). Writes data/local/latest.json, which the
    systemd timer painradar-local-feeds commits + pushes for CI to merge."""
    from radar.collect import LOCAL_FILE, collect_local

    data = collect_local(str(ROOT / "config" / "sources.yml"))
    LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(data['posts'])} posts from {len(data['feeds'])} feeds -> "
          f"{LOCAL_FILE.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    sub.add_parser("check", help="Verify Reddit credentials work")
    sub.add_parser("collect", help="Stage 1: fetch raw posts")
    sub.add_parser("collect-local", help="Home PC only: fetch feeds that block GitHub Actions")
    p_filter = sub.add_parser("filter", help="Stage 2: cut to a shortlist")
    p_filter.add_argument("--show", type=int, default=20,
                          help="how many rows to print (default 20)")
    p_report = sub.add_parser("report", help="Stage 3: AI synthesis -> reports/DATE.md")
    p_report.add_argument("--dry-run", action="store_true",
                          help="print the report but don't write reports/DATE.md")
    p_report.add_argument("--no-telegram", action="store_true",
                          help="skip Telegram even if TG_TOKEN/TG_CHAT_ID are set")

    p_week = sub.add_parser("weekly", help="Stage 4: cluster the pool -> reports/week-DATE.md")
    p_week.add_argument("--until", help="YYYY-MM-DD, last pool day (default: today UTC)")
    p_week.add_argument("--dry-run", action="store_true",
                        help="print the report but don't write reports/")
    p_week.add_argument("--no-telegram", action="store_true",
                        help="skip Telegram even if TG_TOKEN/TG_CHAT_ID are set")

    sub.add_parser("check-competitors",
                   help="Test the competitor check on fixed fake ideas (prints only)")

    p_rev = sub.add_parser("review", help="Two-week review digest -> reports/review-DATE.md")
    p_rev.add_argument("--since", help="YYYY-MM-DD (default: 14 days before --until)")
    p_rev.add_argument("--until", help="YYYY-MM-DD (default: today UTC)")
    p_rev.add_argument("--dry-run", action="store_true", help="print only; write nothing, send nothing")

    args = parser.parse_args()
    load_env()
    return {"check": cmd_check, "collect": cmd_collect,
            "collect-local": cmd_collect_local,
            "filter": cmd_filter, "report": cmd_report,
            "weekly": cmd_weekly, "check-competitors": cmd_check_competitors,
            "review": cmd_review}[args.stage](args)


if __name__ == "__main__":
    raise SystemExit(main())
