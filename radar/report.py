"""Stage 3b: render scored ideas as the Markdown report.

Format matches the original brief exactly: problem one-liner, who has it,
current workaround, 2-3 real links, score breakdown (not just a total),
one suggested first step. "nothing today" if nothing cleared the bar -
never padded to look busy.
"""
from __future__ import annotations

import datetime as dt


def gigs_from_triage(triage: list[dict]) -> list[dict]:
    """Posts triage marked paid_gig (someone hiring). [] when triage failed."""
    return [r for r in triage if r.get("verdict") == "paid_gig"]


def render_gigs(gigs: list[dict], posts_by_id: dict[str, dict]) -> list[str]:
    """Hiring posts: paid work you could take directly. Not scored - not ideas.
    Heading must not match `## N. ` (radar/review.py parses those as ideas)."""
    if not gigs:
        return []
    lines = ["## Gigs — people offering to pay for work", "",
             "Not product ideas: freelance jobs posted today. Check the post date "
             "and replies before answering - good ones go fast.", ""]
    for g in gigs:
        post = posts_by_id.get(g["id"], {})
        lines.append(f"- [{_md_title(post.get('title') or g['id'])}]({post.get('url', '')}) "
                     f"— {post.get('channel', '?')}: {g['reason']}")
    lines.append("")
    return lines


def render(ideas: list[dict], posts_by_id: dict[str, dict], config: dict,
          date: str | None = None, gigs: list[dict] | None = None) -> str:
    date = date or dt.date.today().isoformat()
    w = config["synthesis"]["weights"]

    lines = [f"# Pain Radar — {date}", ""]

    if not ideas:
        lines.append("**Nothing today.** No cluster cleared the filter or the "
                     f"min score bar (`{config['synthesis']['min_total_score']}`) "
                     "this run. See `data/shortlist/` for what was considered.")
        lines.append("")
        lines += render_gigs(gigs or [], posts_by_id)
        return "\n".join(lines).rstrip() + "\n"

    lines.append(f"{len(ideas)} idea{'s' if len(ideas) != 1 else ''} cleared the bar today.")
    lines.append("")

    for i, idea in enumerate(ideas, 1):
        s = idea["scores"]
        lines.append(f"## {i}. {idea['problem_one_line']}")
        lines.append("")
        lines.append(f"**Who:** {idea['who_has_it']}")
        lines.append(f"**Doing about it now:** {idea['current_workaround']}")
        if idea.get("existing_solutions"):
            lines.append(f"**Already exists:** {idea['existing_solutions']} "
                         "*(from the model's knowledge - verify before building)*")
        if idea.get("second_pass"):
            lines.append("*Found on the second clustering pass (triage said real "
                         "problem, the first pass skipped it).*")
        lines.append("")

        lines.append("**Sources:**")
        for pid in idea["source_post_ids"]:
            post = posts_by_id.get(pid)
            if not post:
                continue
            lines.append(f"- [{post['title']}]({post['url']}) — {post['channel']}")
        lines.append("")

        lines.append("**Scores** (1-5 each, money weighted highest):")
        lines.append("")
        lines.append("| Axis | Score | Weight | Weighted |")
        lines.append("|---|---|---|---|")
        for key, label in [("money_evidence", "Money already spent"),
                           ("frequency", "How often it came up"),
                           ("anger", "How angry they sound"),
                           ("ease_to_build", "Easy to build solo")]:
            lines.append(f"| {label} | {s[key]} | {w[key]}x | {s[key] * w[key]:.1f} |")
        lines.append(f"| **Total** | | | **{idea['total_score']}** |")
        lines.append("")

        lines.append(f"**First step:** {idea['first_step']}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines += render_gigs(gigs or [], posts_by_id)
    return "\n".join(lines)


def render_rejected(rejected: list[dict], posts_by_id: dict[str, dict], config: dict,
                    date: str | None = None) -> str:
    """IMPROVEMENT [2026-09-24]: what Gemini clustered but the filters cut, and
    why. Lives in reports/rejected/ (NOT reports/*.md, which the workflow's
    "latest report" glob and "already done today?" gate both read).
    Purpose: tune sources/thresholds from evidence - a cluster cut for a
    low score is a near-miss; one cut for `not near industries` says the
    sources drift outside your list."""
    date = date or dt.date.today().isoformat()
    w = config["synthesis"]["weights"]
    lines = [f"# Rejected clusters — {date}", ""]
    if not rejected:
        lines.append("Gemini returned no clusters that were then cut. "
                     "Either it found no problems at all, or everything it "
                     "found is in the report.")
        return "\n".join(lines) + "\n"
    lines.append(f"{len(rejected)} cluster{'s' if len(rejected) != 1 else ''} "
                 "cut after Gemini clustered them. Not ideas - near-misses and "
                 "the reason each was dropped.")
    lines.append("")
    for i, c in enumerate(rejected, 1):
        s = c.get("scores") or {}
        if not all(k in s for k in w):
            s = {}  # malformed scores: nothing meaningful to print
        total = c.get("total_score")
        if total is None and s:
            try:
                total = round(sum(s[k] * w[k] for k in w), 1)
            except (KeyError, TypeError):
                total = None
        title = c.get("problem_one_line") or "(no title)"
        lines.append(f"## {i}. {title}")
        lines.append("")
        lines.append(f"**Cut because:** {c.get('reject_reason', 'unknown')}"
                     f"{' (second pass)' if c.get('second_pass') else ''}")
        if s:
            lines.append(f"**Scores:** money {s.get('money_evidence')} · "
                         f"frequency {s.get('frequency')} · anger {s.get('anger')} · "
                         f"ease {s.get('ease_to_build')} · total {total}")
        for label, key in [("Industry check", "industry_reason"),
                           ("Buildable check", "buildable_reason"),
                           ("Blocker check", "blocker_reason"),
                           ("Access check", "access_reason"),
                           ("Already exists", "existing_solutions")]:
            if c.get(key):
                lines.append(f"**{label}:** {c[key]}")
        if c.get("who_has_it"):
            lines.append(f"**Who:** {c['who_has_it']}")
        for pid in c.get("source_post_ids") or []:
            post = posts_by_id.get(pid)
            if post:
                lines.append(f"- [{post['title']}]({post['url']}) — {post['channel']}")
        lines.append("")
    return "\n".join(lines)


def render_orphans(triage: list[dict], clusters: list[dict],
                   posts_by_id: dict[str, dict]) -> str:
    """ADDED 2026-09-26: posts triage called real_problem that no cluster
    cited - neither a reported idea nor a cut one. The clustering and triage
    calls disagree run to run (09-26: 4 real_problem, 1 cluster), and these
    posts were otherwise invisible. Not scored - worth a manual look."""
    cited = {pid for c in clusters for pid in (c.get("source_post_ids") or [])}
    orphans = [r for r in triage if r["verdict"] == "real_problem" and r["id"] not in cited]
    if not orphans:
        return ""
    lines = ["", "---", "", "# Real problems that did not become ideas", "",
             f"{len(orphans)} post{'s' if len(orphans) != 1 else ''} triage marked "
             "`real_problem`, but neither clustering pass turned into an idea "
             "(not in the report, not cut above). Unscored - read them yourself; "
             "if one keeps showing up here, it is a missed idea.", ""]
    for r in orphans:
        post = posts_by_id.get(r["id"], {})
        lines.append(f"- [{_md_title((post.get('title') or r['id'])[:80])}]"
                     f"({post.get('url', '')}) ({post.get('channel', '?')}): {r['reason']}")
    return "\n".join(lines) + "\n"


def _md_title(text: str) -> str:
    """Square brackets in a post title (e.g. "[SOLVED] ...") break [text](url)."""
    return (text or "").replace("[", "(").replace("]", ")")


def render_triage(triage: list[dict], posts_by_id: dict[str, dict]) -> str:
    """IMPROVEMENT [2026-09-24]: per-post verdicts + per-source yield. The
    yield table is the point: it says which sources deliver real problems
    and which only pass the keyword filter (billing bug reports etc)."""
    if not triage:
        return ""
    order = ["real_problem", "paid_gig", "help_question", "product_bug_report",
             "out_of_industry", "not_a_problem"]
    counts: dict[str, int] = {}
    per_src: dict[str, dict[str, int]] = {}
    for r in triage:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        ch = posts_by_id.get(r["id"], {}).get("channel", "?")
        per_src.setdefault(ch, {}).setdefault(r["verdict"], 0)
        per_src[ch][r["verdict"]] += 1
    lines = ["", "---", "", "# What Gemini did with each shortlisted post", ""]
    lines.append(f"{len(triage)} posts triaged: " +
                 ", ".join(f"{counts.get(v, 0)} {v}" for v in order) + ".")
    lines += ["", "**Yield by source** (real problems / posts shortlisted):", "",
              "| Source | Real / total | Other verdicts |", "|---|---|---|"]
    for ch, c in sorted(per_src.items(), key=lambda kv: (-kv[1].get("real_problem", 0), -sum(kv[1].values()))):
        others = ", ".join(f"{n} {v}" for v, n in c.items() if v != "real_problem")
        lines.append(f"| {ch} | {c.get('real_problem', 0)} / {sum(c.values())} | {others} |")
    lines += ["", "**Per post:**", ""]
    for v in order:
        for r in triage:
            if r["verdict"] == v:
                post = posts_by_id.get(r["id"], {})
                lines.append(f"- `{v}` — [{_md_title((post.get('title') or r['id'])[:80])}]"
                             f"({post.get('url', '')}) ({post.get('channel', '?')}): {r['reason']}")
    return "\n".join(lines) + "\n"
