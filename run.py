#!/usr/bin/env python3
"""Pain Radar - daily report of real problems people are complaining about.

Usage:
    python3 run.py check       # Verify Reddit credentials
    python3 run.py collect     # Stage 1: fetch raw posts -> data/raw/DATE.json
    python3 run.py filter      # Stage 2: shortlist -> data/shortlist/DATE.json
    python3 run.py report      # Stage 3: AI synthesis -> reports/DATE.md
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
    from radar.report import gigs_from_triage, render, render_rejected, render_triage

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
    ideas = synthesize(posts, config, rejected=rejected, triage=triage, seen=seen)

    posts_by_id = {p["id"]: p for p in posts}
    gigs, old_gigs = drop_seen_gigs(gigs_from_triage(triage), posts_by_id, seen)
    if old_gigs:
        print(f"  dropped {len(old_gigs)} gigs already in an earlier report")
    report_md = render(ideas, posts_by_id, config, date=date, gigs=gigs)
    rejected_md = render_rejected(rejected, posts_by_id, config, date=date)
    rejected_md += render_triage(triage, posts_by_id)
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    sub.add_parser("check", help="Verify Reddit credentials work")
    sub.add_parser("collect", help="Stage 1: fetch raw posts")
    p_filter = sub.add_parser("filter", help="Stage 2: cut to a shortlist")
    p_filter.add_argument("--show", type=int, default=20,
                          help="how many rows to print (default 20)")
    p_report = sub.add_parser("report", help="Stage 3: AI synthesis -> reports/DATE.md")
    p_report.add_argument("--dry-run", action="store_true",
                          help="print the report but don't write reports/DATE.md")
    p_report.add_argument("--no-telegram", action="store_true",
                          help="skip Telegram even if TG_TOKEN/TG_CHAT_ID are set")

    p_rev = sub.add_parser("review", help="Two-week review digest -> reports/review-DATE.md")
    p_rev.add_argument("--since", help="YYYY-MM-DD (default: 14 days before --until)")
    p_rev.add_argument("--until", help="YYYY-MM-DD (default: today UTC)")
    p_rev.add_argument("--dry-run", action="store_true", help="print only; write nothing, send nothing")

    args = parser.parse_args()
    load_env()
    return {"check": cmd_check, "collect": cmd_collect,
            "filter": cmd_filter, "report": cmd_report,
            "review": cmd_review}[args.stage](args)


if __name__ == "__main__":
    raise SystemExit(main())
