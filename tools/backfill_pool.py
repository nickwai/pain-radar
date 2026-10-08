#!/usr/bin/env python3
"""One-off (2026-10-08): seed data/pool/ from the rejected logs written
before pool mode existed, so the first weekly run has two weeks of real
problems instead of a few days.

Reads every `real_problem` line in reports/rejected/DATE.md and re-fetches
the post body: Discourse topics via /t/<id>.json, HN via the Algolia items
API. Anything else (forum RSS) gets title + triage reason only. Skips
sources cut since (CUT_CHANNELS). Never overwrites an existing pool file.

Usage: python3 tools/backfill_pool.py --since 2026-09-29 --until 2026-10-08
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

import requests
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from radar.collect import FEED_UA, record, strip_html  # noqa: E402

LINE_RE = re.compile(r"^- `real_problem` — \[(.+)\]\((https?://[^)\s]+)\) \(([^)]+)\): (.*)$")
CUT_CHANNELS = {"bogleheads", "woocommerce"}


def groups() -> dict[str, str]:
    cfg = yaml.safe_load((ROOT / "config" / "sources.yml").read_text(encoding="utf-8"))
    out = {f["url"].rstrip("/").replace("https://", ""): f.get("group", "general")
           for f in cfg.get("discourse", {}).get("forums", [])}
    out.update({f["name"]: f.get("group", "general") for f in cfg.get("rss", {}).get("feeds", [])})
    return out


def fetch_body(url: str) -> tuple[str, str]:
    """(id, text) - id matches what the collector would have produced."""
    m = re.match(r"^https://([^/]+)/t/(?:[^/]+/)?(\d+)", url)
    if m:
        r = requests.get(f"https://{m.group(1)}/t/{m.group(2)}.json",
                         headers={"User-Agent": FEED_UA}, timeout=20)
        r.raise_for_status()
        return (f"discourse:{m.group(1)}:{m.group(2)}",
                strip_html(r.json()["post_stream"]["posts"][0]["cooked"]))
    m = re.search(r"news\.ycombinator\.com/item\?id=(\d+)", url)
    if m:
        r = requests.get(f"https://hn.algolia.com/api/v1/items/{m.group(1)}", timeout=20)
        r.raise_for_status()
        return f"hn:{m.group(1)}", strip_html(r.json().get("text") or "")
    raise LookupError("no body API for this source")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    args = ap.parse_args()
    grp = groups()
    pool_dir = ROOT / "data" / "pool"
    pool_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted((ROOT / "reports" / "rejected").glob("20*.md")):
        date = f.stem
        if not args.since <= date <= args.until:
            continue
        out_path = pool_dir / f"{date}.json"
        if out_path.exists():
            print(f"{date}: pool file exists, skipped")
            continue
        posts = []
        for line in f.read_text(encoding="utf-8").splitlines():
            m = LINE_RE.match(line)
            if not m:
                continue
            title, url, channel, reason = m.groups()
            if channel in CUT_CHANNELS:
                continue
            try:
                pid, text = fetch_body(url)
                note = ""
            except Exception as exc:  # noqa: BLE001
                pid, text = f"backfill:{url}", ""
                note = f" ({type(exc).__name__}: title + reason only)"
            group = "tech" if channel.startswith("HN:") else grp.get(channel, "general")
            posts.append({**record(id=pid, source="backfill", channel=channel, group=group,
                                   title=title, text=text or f"{title}. {reason}", url=url),
                          "triage_reason": reason, "pooled_on": date})
            print(f"  {date} {channel:<28} {len(text):>5} chars{note}")
            time.sleep(0.7)
        out_path.write_text(json.dumps(posts, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{date}: {len(posts)} posts -> {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
