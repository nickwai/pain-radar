"""Cross-day dedupe (added 2026-09-26).

Forums keep old topics on /latest while they get replies, so the same post
was reaching the report day after day (Shopify email-template idea on 09-24
AND 09-26). No new state file: the committed daily reports already record
every link that was shown, so read them back.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
# `](url)` - robust to square brackets inside idea titles.
LINK_RE = re.compile(r"\]\((https?://[^)\s]+)\)")
# Discourse: /t/<slug>/<id>[/<post>] - slugs can change, the topic id can't.
DISCOURSE_RE = re.compile(r"^(https?://[^/]+)/t/(?:[^/]+/)?(\d+)(?:/\d+)?$")


def norm_url(url: str) -> str:
    url = url.split("#", 1)[0].split("?", 1)[0].rstrip("/").lower()
    m = DISCOURSE_RE.match(url)
    return f"{m.group(1)}/t/{m.group(2)}" if m else url


def reported_urls(reports_dir: Path, before: str, days: int) -> dict[str, str]:
    """{normalised url: latest date it was in a daily report}, for reports in
    [before - days, before). Today's own report is never counted, so a
    same-day re-run doesn't dedupe against itself. days <= 0 disables."""
    if days <= 0:
        return {}
    since = (dt.date.fromisoformat(before) - dt.timedelta(days=days)).isoformat()
    seen: dict[str, str] = {}
    for f in sorted(reports_dir.glob("*.md")):
        m = DATE_RE.match(f.name)  # skips review-*.md; rejected/ is a subdir
        if not m or not since <= m.group(1) < before:
            continue
        for url in LINK_RE.findall(f.read_text(encoding="utf-8")):
            seen[norm_url(url)] = m.group(1)
    return seen


def drop_seen_ideas(ideas: list[dict], posts_by_id: dict[str, dict],
                    seen: dict[str, str],
                    rejected: list[dict] | None = None) -> list[dict]:
    """Drop an idea only if EVERY post it cites was already reported. One new
    post on the same problem keeps it - that is repeat evidence, not a rerun."""
    if not seen:
        return ideas
    out = []
    for idea in ideas:
        dates = [seen.get(norm_url(posts_by_id.get(pid, {}).get("url", "")))
                 for pid in idea["source_post_ids"]]
        if all(dates):
            if rejected is not None:
                rejected.append({**idea, "reject_reason":
                                 f"already reported (last on {max(dates)})"})
            continue
        out.append(idea)
    return out


def drop_seen_gigs(gigs: list[dict], posts_by_id: dict[str, dict],
                   seen: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """(new gigs, gigs already reported)."""
    new, old = [], []
    for g in gigs:
        url = posts_by_id.get(g["id"], {}).get("url", "")
        (old if url and norm_url(url) in seen else new).append(g)
    return new, old
