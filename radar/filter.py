"""Stage 2: cut hundreds of raw posts down to a shortlist worth paying an AI for.

Pure regex and arithmetic. No API calls, no cost. Everything that decides
the outcome lives in config/keywords.yml and config/scoring.yml.
"""
from __future__ import annotations

import re
from typing import Any

import yaml


def load_configs(kw_path: str, sc_path: str) -> tuple[dict, dict]:
    with open(kw_path, encoding="utf-8") as fh:
        keywords = yaml.safe_load(fh)
    with open(sc_path, encoding="utf-8") as fh:
        scoring = yaml.safe_load(fh)
    return keywords, scoring


def compile_phrases(phrases: list[str]) -> re.Pattern:
    """One regex for a whole list. Word-ish boundaries so 'rip ' matches 'rip '."""
    escaped = [re.escape(p) for p in phrases]
    return re.compile("|".join(escaped), re.IGNORECASE)


def compile_regexes(patterns: list[str]) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


def normalise_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def score_post(post: dict, pats: dict, scoring: dict) -> dict:
    blob = f"{post['title']} {post['text']}"
    weights = scoring["weights"]
    caps = scoring["caps"]

    money_hits = pats["money"].findall(blob)
    pain_hits = pats["pain"].findall(blob)
    cash_hits = pats["money_regex"].findall(blob)

    n_money = min(len(money_hits), caps["money"])
    n_pain = min(len(pain_hits), caps["pain"])
    n_cash = min(len(cash_hits), caps["money_regex"])

    # Replies matter more than upvotes: a reply means someone cared enough to type.
    raw_engagement = post["comments"] * 0.4 + post["score"] * 0.1
    engagement = min(raw_engagement, caps["engagement"])

    # A dollar amount only counts when a real money phrase sits beside it.
    # Otherwise every for-sale listing outranks every genuine complaint.
    cash_value = n_cash * weights["money_regex"] if n_money else 0.0

    # The thing you actually asked for: pain AND money in the same post.
    combo = weights.get("combo_bonus", 0.0) if (n_pain and (n_money or n_cash)) else 0.0

    subtotal = (
        n_money * weights["money"]
        + cash_value
        + n_pain * weights["pain"]
        + engagement * weights["engagement"]
        + combo
    )
    multiplier = scoring["group_multiplier"].get(post["group"], 1.0)

    return {
        "combo": bool(combo),
        "money": n_money,
        "cash": n_cash,
        "pain": n_pain,
        "engagement": round(engagement, 2),
        "multiplier": multiplier,
        "score": round(subtotal * multiplier, 2),
        # Kept so you can see WHY something scored - useful when tuning.
        "money_matched": sorted({m.lower() for m in money_hits})[:6],
        "pain_matched": sorted({p.lower() for p in pain_hits})[:6],
        "cash_matched": [c if isinstance(c, str) else "".join(c)
                         for c in cash_hits][:4],
    }


def shortlist(posts: list[dict], keywords: dict, scoring: dict,
              verbose: bool = True) -> tuple[list[dict], dict]:
    pats = {
        "money": compile_phrases(keywords["money"]),
        "pain": compile_phrases(keywords["pain"]),
        "money_regex": compile_regexes(keywords["money_regex"]),
        "exclude": compile_phrases(keywords["exclude"]),
        "exclude_soft": compile_phrases(keywords["exclude_soft"]),
    }
    rules = scoring["shortlist"]
    stats = {"start": len(posts), "excluded": 0, "too_short": 0,
             "low_score": 0, "duplicate": 0, "no_signal": 0}

    scored: list[dict] = []
    seen_titles: set[str] = set()

    for post in posts:
        blob = f"{post['title']} {post['text']}"

        if pats["exclude"].search(post["title"]) or pats["exclude_soft"].search(post["title"]):
            stats["excluded"] += 1
            continue

        key = normalise_title(post["title"])
        if key and key in seen_titles:
            stats["duplicate"] += 1
            continue
        seen_titles.add(key)

        breakdown = score_post(post, pats, scoring)

        # Short posts are usually noise - unless real money is named.
        if len(blob) < rules["min_chars"] and not breakdown["cash"]:
            stats["too_short"] += 1
            continue

        if rules.get("require_signal") and not (breakdown["pain"] or breakdown["money"]):
            stats["no_signal"] += 1
            continue

        if breakdown["score"] < rules["min_score"]:
            stats["low_score"] += 1
            continue

        scored.append({**post, "signals": breakdown})

    scored.sort(key=lambda p: p["signals"]["score"], reverse=True)

    # Per-group quota so one industry cannot swallow the whole report.
    per_group: dict[str, int] = {}
    picked: list[dict] = []
    for post in scored:
        group = post["group"]
        if per_group.get(group, 0) >= rules["max_per_group"]:
            continue
        per_group[group] = per_group.get(group, 0) + 1
        picked.append(post)
        if len(picked) >= rules["total"]:
            break

    stats["scored"] = len(scored)
    stats["picked"] = len(picked)
    stats["per_group"] = per_group

    if verbose:
        print(f"  start        {stats['start']:>4}")
        print(f"  -excluded    {stats['excluded']:>4}  (noise words in title)")
        print(f"  -duplicate   {stats['duplicate']:>4}  (same title seen already)")
        print(f"  -too short   {stats['too_short']:>4}  (under {rules['min_chars']} chars, no money)")
        print(f"  -no signal   {stats['no_signal']:>4}  (a price tag but no pain or money phrase)")
        print(f"  -low score   {stats['low_score']:>4}  (below {rules['min_score']})")
        print(f"  = survived   {stats['scored']:>4}")
        print(f"  = shortlist  {stats['picked']:>4}  (capped {rules['max_per_group']}/group)")

    return picked, stats


def preview(picked: list[dict], limit: int = 20) -> None:
    """Human-readable table so you can sanity-check before spending tokens."""
    print(f"\n{'score':>6} {'combo':>5} {'$':>2} {'pain':>4}  "
          f"{'group':<11} {'channel':<22} title")
    print("-" * 118)
    for post in picked[:limit]:
        sig = post["signals"]
        mark = "  YES" if sig.get("combo") else "    -"
        print(f"{sig['score']:>6.1f} {mark:>5} {sig['money'] + sig['cash']:>2} "
              f"{sig['pain']:>4}  {post['group']:<11} "
              f"{post['channel'][:22]:<22} {post['title'][:48]}")
