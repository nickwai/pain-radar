"""Stage 3b: render scored ideas as the Markdown report.

Format matches the original brief exactly: problem one-liner, who has it,
current workaround, 2-3 real links, score breakdown (not just a total),
one suggested first step. "nothing today" if nothing cleared the bar -
never padded to look busy.
"""
from __future__ import annotations

import datetime as dt


def render(ideas: list[dict], posts_by_id: dict[str, dict], config: dict,
          date: str | None = None) -> str:
    date = date or dt.date.today().isoformat()
    w = config["synthesis"]["weights"]

    lines = [f"# Pain Radar — {date}", ""]

    if not ideas:
        lines.append("**Nothing today.** No cluster cleared the filter or the "
                     f"min score bar (`{config['synthesis']['min_total_score']}`) "
                     "this run. See `data/shortlist/` for what was considered.")
        return "\n".join(lines) + "\n"

    lines.append(f"{len(ideas)} idea{'s' if len(ideas) != 1 else ''} cleared the bar today.")
    lines.append("")

    for i, idea in enumerate(ideas, 1):
        s = idea["scores"]
        lines.append(f"## {i}. {idea['problem_one_line']}")
        lines.append("")
        lines.append(f"**Who:** {idea['who_has_it']}")
        lines.append(f"**Doing about it now:** {idea['current_workaround']}")
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

    return "\n".join(lines)
