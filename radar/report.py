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


def render_competitors(cc: dict | None) -> list[str]:
    """ADDED 2026-10-08: radar/competitors.py result. Verified = the name came
    from a real search result (link shown); unverified = model memory."""
    if not cc:
        return []
    lines = [f"**Competitor check:** {cc['verdict']}"
             + (f" — {cc['gap']}" if cc.get("gap") else "")]
    for c in cc.get("competitors", []):
        name = f"[{_md_title(c['name'])}]({c['url']})" if c.get("url") else \
            f"{c['name']} *(from model memory, unverified)*"
        covers = {"main_use": " — covers the main use", "part": " — covers part"}.get(
            c.get("covers", ""), "")
        if c.get("kind") == "big_suite":
            covers += " (big suite - not counted)"
        lines.append(f"- {name}{covers}: {c.get('note', '')}")
    if cc.get("queries"):
        lines.append(f"*Searched HN + GitHub for: {'; '.join(cc['queries'])}*")
    return lines


def render_jobs(jobs: list[dict] | None, gigs_by_id: dict[str, dict],
                n_gigs: int) -> list[str]:
    """ADDED 2026-10-08 (radar/gigs.py): tasks different people paid for.
    jobs None = check failed/off. Heading must not match `## N. `."""
    lines = ["## Repeated paid jobs", ""]
    if jobs is None:
        return lines + [f"*Check did not run ({n_gigs} gigs in the window).*", ""]
    if not jobs:
        return lines + [f"No task was paid for twice among {n_gigs} gigs in the window.", ""]
    lines += [f"Tasks that different people paid for, from {n_gigs} gigs in the window. "
              "Not scored - leads: a job people keep hiring for is one a tool could do.", ""]
    for j in jobs:
        lines.append(f"**{j['job_one_line']}** — {len(j['gig_ids'])} posts")
        lines.append(f"- Who pays: {j['who_pays']}")
        if j.get("productizable") and j.get("product_idea"):
            lines.append(f"- Could be a product: {j['product_idea']}")
        else:
            lines.append("- Not productizable (needs a person each time)")
        lines.append(f"- Evidence: {j['why']}")
        for gid in j["gig_ids"]:
            g = gigs_by_id.get(gid, {})
            lines.append(f"  - [{_md_title(g.get('title') or gid)}]({g.get('url', '')}) "
                         f"— {g.get('channel', '?')}, {g.get('pooled_on', '?')}")
        lines.append("")
    return lines


def render(ideas: list[dict], posts_by_id: dict[str, dict], config: dict,
          date: str | None = None, gigs: list[dict] | None = None,
          period: str | None = None, intro: str = "",
          jobs_section: list[str] | None = None) -> str:
    """period (weekly report, 2026-10-08): e.g. "2026-09-28 → 2026-10-12",
    used in the title and wording instead of a single day."""
    date = date or dt.date.today().isoformat()
    w = config["synthesis"]["weights"]
    when = "this week" if period else "today"

    lines = [f"# Pain Radar — {'week ' + period if period else date}", ""]
    if intro:
        lines += [intro, ""]

    if not ideas:
        lines.append(f"**Nothing {when}.** No cluster cleared the filter or the "
                     f"min score bar (`{config['synthesis']['min_total_score']}`, "
                     f"money ≥ `{config['synthesis']['min_money_evidence']}`) "
                     "or the competitor check this run. See the rejected log for "
                     "what was considered.")
        lines.append("")
        lines += jobs_section or []
        lines += render_gigs(gigs or [], posts_by_id)
        return "\n".join(lines).rstrip() + "\n"

    lines.append(f"{len(ideas)} idea{'s' if len(ideas) != 1 else ''} cleared the bar {when}.")
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
        if idea.get("access_reason"):
            lines.append(f"**Access check:** {idea['access_reason']}")
        if idea.get("second_pass"):
            lines.append("*Found on the second clustering pass (triage said real "
                         "problem, the first pass skipped it).*")
        lines.append("")
        comp = render_competitors(idea.get("competitor_check"))
        if comp:
            lines += comp + [""]

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

    lines += jobs_section or []
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
        lines += render_competitors(c.get("competitor_check"))
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
    order = ["real_problem", "paid_gig", "self_promo", "help_question",
             "product_bug_report", "out_of_industry", "not_a_problem"]
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


def render_daily_pool(date: str, pooled: list[dict], pool_size: int, days: int,
                      next_weekly: str, gigs: list[dict],
                      posts_by_id: dict[str, dict], triage_ok: bool) -> str:
    """ADDED 2026-10-08: daily report in pool mode. No clustering today - the
    real problems found go to data/pool/ and are clustered together weekly.
    Must not contain `## N. ` headings (review.py reads those as ideas)."""
    lines = [f"# Pain Radar — {date}", ""]
    if not triage_ok:
        lines += ["**Triage failed today** - nothing was added to the pool. "
                  "Check the Stage 3 log for `[triage] skipped`.", ""]
    else:
        lines += [f"**{len(pooled)} real problem{'s' if len(pooled) != 1 else ''} added "
                  f"to the pool today.** Pool now holds {pool_size} over the last "
                  f"{days} days. Ideas are clustered from the whole pool weekly - "
                  f"next: {next_weekly} (`reports/week-{next_weekly}.md`).", ""]
        if pooled:
            # <url> autolinks, NOT [title](url): radar/history.py treats every
            # `](url)` in reports/DATE.md as already reported, which would make
            # the weekly run drop the very posts it pooled.
            lines += ["## Pooled today", ""]
            for p in pooled:
                lines.append(f"- {_md_title(p['title'][:90])} ({p['channel']}): "
                             f"{p['triage_reason']} <{p['url']}>")
            lines.append("")
    lines += render_gigs(gigs, posts_by_id)
    return "\n".join(lines).rstrip() + "\n"
