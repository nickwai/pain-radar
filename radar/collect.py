"""Stage 1: pull raw posts from every configured source into one list.

Every collector is wrapped so one dead source can never kill the run.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import html
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import Any

import requests
import yaml

# Some forums (XenForo, Invision) reject bare python-requests.
FEED_UA = ("Mozilla/5.0 (compatible; pain-radar/0.1; personal research script)")
UA = os.environ.get("REDDIT_USER_AGENT", FEED_UA)
TIMEOUT = 25
TAG_RE = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------- helpers

def log(msg: str) -> None:
    print(msg, flush=True)


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", text))).strip()


def parse_date(value: str | None) -> int:
    """Handle both ISO-8601 (Atom, Discourse) and RFC-822 (RSS pubDate)."""
    if not value:
        return 0
    value = value.strip()
    try:
        return int(dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        pass
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return int(parsed.timestamp())
    except (TypeError, ValueError):
        return 0


def clean_title(title: str) -> str:
    """Feeds prefix titles: 'Board Name • Re: Actual Topic'. Strip that."""
    title = (title or "").strip()
    if "•" in title:
        title = title.rsplit("•", 1)[-1].strip()
    return re.sub(r"^(re|rfc)\s*:\s*", "", title, flags=re.IGNORECASE).strip()


def record(**kw: Any) -> dict:
    """Normalise every source into one shape."""
    return {
        "id": kw["id"],
        "source": kw["source"],
        "channel": kw["channel"],
        "group": kw.get("group", "general"),
        "title": clean_title(kw.get("title")),
        "text": (kw.get("text") or "").strip()[:4000],
        "url": kw["url"],
        "created_utc": int(kw.get("created_utc") or 0),
        "score": int(kw.get("score") or 0),
        "comments": int(kw.get("comments") or 0),
    }


def safe(name: str, fn, *args, **kw) -> list[dict]:
    try:
        out = fn(*args, **kw)
        log(f"  {name:<32} {len(out):>4} posts")
        return out
    except Exception as exc:  # noqa: BLE001 - one bad source must not stop the run
        log(f"  {name:<32} FAILED: {type(exc).__name__}: {exc}")
        return []


# ---------------------------------------------------------------- rss / atom

def _first_text(node: ET.Element, names: list[str]) -> str:
    """Find the first matching child, ignoring XML namespaces."""
    for child in node.iter():
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag in names and (child.text or "").strip():
            return child.text
    return ""


def _link_of(node: ET.Element) -> str:
    for child in node.iter():
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag == "link":
            if child.get("href"):
                return child.get("href", "")
            if (child.text or "").strip():
                return child.text.strip()
    return ""


def parse_feed(xml_bytes: bytes, name: str, group: str) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out: list[dict] = []
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1].lower()
        if tag not in ("item", "entry"):
            continue
        link = _link_of(node)
        if not link:
            continue
        title = strip_html(_first_text(node, ["title"]))
        body = strip_html(_first_text(node, ["description", "content", "summary",
                                             "encoded"]))
        created = parse_date(_first_text(node, ["pubdate", "published", "updated",
                                                "date"]))
        out.append(record(
            id=f"rss:{name}:{link}",
            source="rss",
            channel=name,
            group=group,
            title=title,
            text=body,
            url=link,
            created_utc=created,
        ))
    return out


def fetch_rss(cfg: dict, cutoff: int) -> list[dict]:
    out: list[dict] = []
    for feed in cfg.get("feeds", []):
        name = feed.get("name") or feed["url"]
        # Optional paging (added 2026-09-26) for feeds that support it
        # (Invision: page_url with {page}); stop once past the lookback.
        items: list[dict] = []
        pages = 0
        for page in range(1, (feed.get("max_pages", 1) if feed.get("page_url") else 1) + 1):
            url = feed["url"] if page == 1 else feed["page_url"].format(page=page)
            try:
                resp = requests.get(url, headers={"User-Agent": FEED_UA},
                                    timeout=TIMEOUT)
                if resp.status_code != 200:
                    log(f"  {name:<18} HTTP {resp.status_code}"
                        f"{f' (page {page})' if page > 1 else ''}")
                    break
                batch = parse_feed(resp.content, name, feed.get("group", "general"))
            except Exception as exc:  # noqa: BLE001
                log(f"  {name:<18} {type(exc).__name__}: {exc}")
                break
            pages += 1
            known = {i["id"] for i in items}
            items += [i for i in batch if i["id"] not in known]
            dated = [i["created_utc"] for i in batch if i["created_utc"]]
            if not batch or not dated or min(dated) < cutoff:
                break
            time.sleep(0.8)
        if not pages:
            continue
        # Extra feeds merged in, e.g. a quiet forum's reply feed next to its
        # new-threads feed (trade2win: 1 new thread in 48h, 11 recent replies).
        for extra in feed.get("also_urls", []):
            time.sleep(0.8)
            try:
                resp = requests.get(extra, headers={"User-Agent": FEED_UA},
                                    timeout=TIMEOUT)
                if resp.status_code == 200:
                    known = {i["id"] for i in items}
                    items += [i for i in parse_feed(resp.content, name,
                                                    feed.get("group", "general"))
                              if i["id"] not in known]
            except Exception:  # noqa: BLE001 - the main feed already worked
                pass
        # Many forum feeds omit dates; keep those rather than lose the source.
        kept = [i for i in items if i["created_utc"] == 0 or i["created_utc"] >= cutoff]
        dated = [i["created_utc"] for i in kept if i["created_utc"]]
        span = f"  spans {(max(dated) - min(dated)) / 3600:.1f}h" if dated else ""
        log(f"  {name:<18} {len(kept):>3} kept / {len(items):>3} in feed{span}"
            f"{f'  pages={pages}' if pages > 1 else ''}")
        out += kept
        time.sleep(0.8)
    return out


# ---------------------------------------------------------------- discourse

def discourse_bodies(base: str, pages: int = 1) -> dict[str, str]:
    """/latest.json has no post text; /latest.rss does. Join them on topic id.
    `pages`: fetch as many RSS pages as JSON pages were fetched (2026-09-26)."""
    bodies: dict[str, str] = {}
    for page in range(pages):
        try:
            resp = requests.get(f"{base}/latest.rss", params={"page": page} if page else None,
                                headers={"User-Agent": FEED_UA}, timeout=TIMEOUT)
            if resp.status_code != 200:
                break
            for item in parse_feed(resp.content, "tmp", "tmp"):
                match = re.search(r"/t/[^/]+/(\d+)", item["url"])
                if match:
                    bodies.setdefault(match.group(1), item["text"])
        except Exception:  # noqa: BLE001 - body text is a bonus, never a blocker
            break
        if page + 1 < pages:
            time.sleep(0.6)
    return bodies


def fetch_discourse(cfg: dict, cutoff: int) -> list[dict]:
    out: list[dict] = []
    for forum in cfg.get("forums", []):
        base = forum["url"].rstrip("/")
        short = base.replace("https://", "")
        # Page until the oldest topic is past the lookback (added 2026-09-26:
        # n8n's 30 newest topics span ~18h, so page 1 alone missed posts).
        topics: list[dict] = []
        pages = 0
        for page in range(cfg.get("max_pages", 1)):
            try:
                params = {"order": "created", **({"page": page} if page else {})}
                resp = requests.get(f"{base}/latest.json", params=params,
                                    headers={"User-Agent": FEED_UA}, timeout=TIMEOUT)
                if resp.status_code != 200:
                    log(f"  {short:<30} HTTP {resp.status_code} (page {page + 1})")
                    break
                data = resp.json().get("topic_list", {})
            except Exception as exc:  # noqa: BLE001
                log(f"  {short:<30} {type(exc).__name__} (page {page + 1})")
                break
            batch = data.get("topics", [])
            pages += 1
            topics += batch
            unpinned = [parse_date(t.get("created_at")) for t in batch if not t.get("pinned")]
            if not batch or not data.get("more_topics_url") or not unpinned \
                    or min(unpinned) < cutoff:
                break
            time.sleep(0.6)
        if not pages:
            continue

        time.sleep(0.6)
        bodies = discourse_bodies(base, pages)
        seen_ids: set[int] = set()

        kept = 0
        for topic in topics:
            created = parse_date(topic.get("created_at"))
            if created < cutoff or topic.get("pinned") or topic["id"] in seen_ids:
                continue
            seen_ids.add(topic["id"])
            body = bodies.get(str(topic["id"])) or strip_html(topic.get("excerpt"))
            out.append(record(
                id=f"discourse:{short}:{topic['id']}",
                source="discourse",
                channel=short,
                group=forum.get("group", "general"),
                title=topic.get("title"),
                text=body,
                url=f"{base}/t/{topic.get('slug')}/{topic['id']}",
                created_utc=created,
                score=topic.get("like_count"),
                comments=max((topic.get("posts_count") or 1) - 1, 0),
            ))
            kept += 1
        flag = f"bodies={len(bodies)}" if bodies else "bodies=0 (rss blocked)"
        log(f"  {short:<30} {kept:>3} kept / {len(topics):>3} latest  {flag}"
            f"{f'  pages={pages}' if pages > 1 else ''}")
        time.sleep(0.6)
    return out


# ---------------------------------------------------------------- hn / lobsters / se

def _norm_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u2019", "'")).lower()


def fetch_hackernews(cfg: dict, cutoff: int) -> list[dict]:
    """FIX [2026-09-26]: Algolia matches loosely (prefixes, any word order,
    words missing), so only ~1% of hits for "we pay for" contained the
    phrase, and 30 hits covered ~2h of the 48h window. Now: fetch the whole
    window in one request (hitsPerPage up to 1000) and, with phrase_match,
    keep only hits whose text really contains the query phrase."""
    out: list[dict] = []
    phrase_match = cfg.get("phrase_match", True)
    for query in cfg.get("queries", []):
        resp = requests.get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={
                "query": query,
                "tags": "(story,comment)",
                "numericFilters": f"created_at_i>{cutoff}",
                "hitsPerPage": cfg.get("hits_per_query", 30),
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", [])
        kept = 0
        for hit in hits:
            title = hit.get("title") or hit.get("story_title") or ""
            text = strip_html(hit.get("story_text") or hit.get("comment_text"))
            if phrase_match and _norm_phrase(query) not in _norm_phrase(f"{title} {text}"):
                continue
            kept += 1
            out.append(record(
                id=f"hn:{hit['objectID']}",
                source="hackernews",
                channel=f"HN:{query}",
                group="tech",
                title=title,
                text=text,
                url=f"https://news.ycombinator.com/item?id={hit['objectID']}",
                created_utc=hit.get("created_at_i"),
                score=hit.get("points"),
                comments=hit.get("num_comments"),
            ))
        more = " (window NOT fully covered)" if data.get("nbHits", 0) > len(hits) else ""
        log(f"  HN {query!r:<28} {kept:>3} kept / {len(hits):>4} hits{more}")
        time.sleep(0.4)
    if cfg.get("ask_hn"):
        resp = requests.get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={"tags": "ask_hn", "numericFilters": f"created_at_i>{cutoff}",
                    "hitsPerPage": cfg.get("hits_per_query", 30)},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        for hit in hits:
            out.append(record(
                id=f"hn:{hit['objectID']}",
                source="hackernews",
                channel="HN:ask",
                group="tech",
                title=hit.get("title") or "",
                text=strip_html(hit.get("story_text")),
                url=f"https://news.ycombinator.com/item?id={hit['objectID']}",
                created_utc=hit.get("created_at_i"),
                score=hit.get("points"),
                comments=hit.get("num_comments"),
            ))
        log(f"  HN {'Ask HN':<28} {len(hits):>3} stories")
    return out


def fetch_lobsters(_cfg: dict, cutoff: int) -> list[dict]:
    resp = requests.get("https://lobste.rs/newest.json",
                        headers={"User-Agent": FEED_UA}, timeout=TIMEOUT)
    resp.raise_for_status()
    out = []
    for item in resp.json():
        created = parse_date(item.get("created_at"))
        if created < cutoff:
            continue
        out.append(record(
            id=f"lobsters:{item['short_id']}",
            source="lobsters",
            channel="lobste.rs",
            group="tech",
            title=item.get("title"),
            text=strip_html(item.get("description")),
            url=item.get("comments_url") or item.get("url"),
            created_utc=created,
            score=item.get("score"),
            comments=item.get("comment_count"),
        ))
    return out


def fetch_stackexchange(cfg: dict, cutoff: int) -> list[dict]:
    out: list[dict] = []
    for site in cfg.get("sites", []):
        resp = requests.get(
            "https://api.stackexchange.com/2.3/questions",
            params={"site": site, "order": "desc", "sort": "creation",
                    "pagesize": cfg.get("page_size", 30),
                    "fromdate": cutoff, "filter": "withbody"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        for item in resp.json().get("items", []):
            out.append(record(
                id=f"se:{site}:{item['question_id']}",
                source="stackexchange",
                channel=f"{site}.stackexchange",
                group=site,
                title=item.get("title"),
                text=strip_html(item.get("body")),
                url=item.get("link"),
                created_utc=item.get("creation_date"),
                score=item.get("score"),
                comments=item.get("answer_count"),
            ))
        time.sleep(0.5)
    return out


# ---------------------------------------------------------------- reddit (off)

def fetch_reddit(cfg: dict, cutoff: int) -> list[dict]:
    """Only runs if reddit.enabled is true AND you have approved API creds.

    Reddit disabled self-serve API keys in 2025 (Responsible Builder Policy).
    Public .json returns 403. Left here so it works the day you get access.
    """
    cid = os.environ.get("REDDIT_CLIENT_ID")
    secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and secret):
        raise RuntimeError("reddit.enabled is true but REDDIT_CLIENT_ID/SECRET are unset")

    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    resp = sess.post("https://www.reddit.com/api/v1/access_token",
                     auth=(cid, secret), data={"grant_type": "client_credentials"},
                     timeout=TIMEOUT)
    resp.raise_for_status()
    sess.headers["Authorization"] = f"bearer {resp.json()['access_token']}"

    out: list[dict] = []
    for group, subs in cfg.get("subreddits", {}).items():
        for sub in subs:
            for endpoint in cfg.get("endpoints", ["new"]):
                joiner = "&" if "?" in endpoint else "?"
                url = (f"https://oauth.reddit.com/r/{sub}/{endpoint}"
                       f"{joiner}limit={cfg.get('limit', 50)}&raw_json=1")
                try:
                    r = sess.get(url, timeout=TIMEOUT)
                    if r.status_code != 200:
                        log(f"  r/{sub:<20} {endpoint:<10} HTTP {r.status_code}")
                        continue
                    children = r.json()["data"]["children"]
                except Exception as exc:  # noqa: BLE001
                    log(f"  r/{sub:<20} {endpoint:<10} {type(exc).__name__}")
                    continue
                for child in children:
                    d = child["data"]
                    if d.get("created_utc", 0) < cutoff or d.get("stickied"):
                        continue
                    out.append(record(
                        id=f"reddit:{d['id']}", source="reddit",
                        channel=f"r/{sub}", group=group,
                        title=d.get("title"), text=d.get("selftext"),
                        url=f"https://reddit.com{d['permalink']}",
                        created_utc=d.get("created_utc"),
                        score=d.get("score"), comments=d.get("num_comments"),
                    ))
                time.sleep(0.9)
    return out


# ---------------------------------------------------------------- entry

def collect(config_path: str = "config/sources.yml") -> list[dict]:
    with open(config_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    cutoff = int(time.time()) - cfg.get("lookback_hours", 48) * 3600
    stamp = dt.datetime.fromtimestamp(cutoff, dt.timezone.utc)
    log(f"Collecting posts newer than {stamp:%Y-%m-%d %H:%M} UTC\n")

    posts: list[dict] = []
    if cfg.get("reddit", {}).get("enabled"):
        log("reddit:")
        posts += safe("reddit TOTAL", fetch_reddit, cfg["reddit"], cutoff)
    if cfg.get("discourse"):
        log("discourse forums:")
        posts += safe("discourse TOTAL", fetch_discourse, cfg["discourse"], cutoff)
    if cfg.get("rss"):
        log("rss feeds:")
        posts += safe("rss TOTAL", fetch_rss, cfg["rss"], cutoff)
    if cfg.get("hackernews"):
        log("hackernews:")
        posts += safe("hn algolia", fetch_hackernews, cfg["hackernews"], cutoff)
    if cfg.get("lobsters", {}).get("enabled"):
        log("lobsters:")
        posts += safe("lobste.rs", fetch_lobsters, cfg["lobsters"], cutoff)
    if cfg.get("stackexchange"):
        log("stackexchange:")
        posts += safe("stack exchange", fetch_stackexchange, cfg["stackexchange"], cutoff)

    seen: set[str] = set()
    unique = []
    for post in posts:
        if post["id"] in seen:
            continue
        seen.add(post["id"])
        unique.append(post)
    log(f"\nRaw: {len(posts)}  |  Unique: {len(unique)}")
    return unique
