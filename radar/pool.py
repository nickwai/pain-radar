"""Rolling pool of real problems (added 2026-10-08, from the 2-week review).

The review showed each day's ~5 real_problem posts being clustered alone:
a pain seen once a day never gathers the repeat evidence to score well, so
13 of 15 days produced nothing worth building. Now the daily run only
triages and saves its real_problem posts here (data/pool/DATE.json,
committed by CI); the weekly run clusters the whole window at once, so the
same problem hit by three people on three days becomes ONE strong cluster.

A forum topic stays on /latest for days and gets triaged again each day:
load_window() keeps one copy per topic (norm_url), the newest, so repeats
of the same post never pass as frequency.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from radar.history import norm_url

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")


def save_day(pool_dir: Path, date: str, posts: list[dict],
             triage: list[dict]) -> list[dict]:
    """Write the day's real_problem posts (full post + triage reason).
    Returns what was written. An empty triage (call failed) writes nothing,
    so a failed day never overwrites a good file from an earlier run."""
    if not triage:
        return []
    reasons = {r["id"]: r["reason"] for r in triage if r["verdict"] == "real_problem"}
    real = [{**p, "triage_reason": reasons[p["id"]], "pooled_on": date}
            for p in posts if p["id"] in reasons]
    pool_dir.mkdir(parents=True, exist_ok=True)
    (pool_dir / f"{date}.json").write_text(
        json.dumps(real, indent=2, ensure_ascii=False), encoding="utf-8")
    return real


def load_window(pool_dir: Path, until: str, days: int) -> list[dict]:
    """Every pooled post from (until - days, until], one per topic, newest wins."""
    since = (dt.date.fromisoformat(until) - dt.timedelta(days=days)).isoformat()
    by_url: dict[str, dict] = {}
    for f in sorted(pool_dir.glob("*.json")) if pool_dir.exists() else []:
        m = DATE_RE.match(f.name)
        if not m or not since < m.group(1) <= until:
            continue
        for p in json.loads(f.read_text(encoding="utf-8")):
            by_url[norm_url(p.get("url") or p["id"])] = p
    return list(by_url.values())
