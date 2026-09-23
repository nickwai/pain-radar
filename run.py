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
    from radar.synthesize import synthesize
    from radar.report import render

    shortlist_dir = ROOT / "data" / "shortlist"
    files = sorted(shortlist_dir.glob("*.json"))
    if not files:
        print("No shortlist. Run: python3 run.py collect && python3 run.py filter")
        return 1
    shortlist_path = files[-1]
    posts = json.loads(shortlist_path.read_text(encoding="utf-8"))
    print(f"Synthesizing {shortlist_path.name} ({len(posts)} posts)\n")

    config = yaml.safe_load((ROOT / "config" / "scoring.yml").read_text(encoding="utf-8"))
    ideas = synthesize(posts, config)

    posts_by_id = {p["id"]: p for p in posts}
    date = shortlist_path.stem
    report_md = render(ideas, posts_by_id, config, date=date)

    print("\n" + "=" * 60)
    print(report_md)

    if args.dry_run:
        print("(--dry-run: not writing to reports/)")
        return 0

    out_path = ROOT / "reports" / f"{date}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_md, encoding="utf-8")
    print(f"\nWrote report -> {out_path.relative_to(ROOT)}")
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

    args = parser.parse_args()
    load_env()
    return {"check": cmd_check, "collect": cmd_collect,
            "filter": cmd_filter, "report": cmd_report}[args.stage](args)


if __name__ == "__main__":
    raise SystemExit(main())
