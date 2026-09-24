"""Two-week review digest (built 2026-09-24, first run 2026-10-08).

Reads what the daily runs already committed - reports/DATE.md and
reports/rejected/DATE.md - and summarises them so the review is about
evidence, not memory. READ-ONLY on those files; writes only the digest.

It reports; it does not decide. The checklist at the end is for a human (or
a Claude session) to work through - nothing here changes sources or config.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


def _dates(folder: Path, since: str) -> list[str]:
    out = []
    for f in sorted(folder.glob("*.md")):
        m = DATE_RE.match(f.name)
        if m and m.group(1) >= since:
            out.append(m.group(1))
    return out


def parse_report(text: str) -> list[dict]:
    """[{title, total}] for each idea in a daily report ('Nothing today' -> [])."""
    ideas = []
    for block in re.split(r"\n(?=## \d+\. )", text)[1:]:
        title = re.match(r"## \d+\. (.+)", block).group(1).strip()
        m = re.search(r"\| \*\*Total\*\* \|[^|]*\|[^|]*\| \*\*([\d.]+)\*\*", block)
        ideas.append({"title": title, "total": float(m.group(1)) if m else None})
    return ideas


def parse_yield(text: str) -> dict[str, tuple[int, int]]:
    """{source: (real, total)} from the 'Yield by source' table."""
    out = {}
    for m in re.finditer(r"^\| ([^|]+?) \| (\d+) / (\d+) \|", text, re.M):
        if m.group(1) in ("Source", "---"):
            continue
        out[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    return out


def build(reports_dir: Path, since: str, until: str) -> tuple[str, str]:
    """Returns (full_markdown, short_telegram_text)."""
    days = [d for d in _dates(reports_dir, since) if d <= until]
    rej_dir = reports_dir / "rejected"
    per_day = {}
    for d in days:
        per_day[d] = parse_report((reports_dir / f"{d}.md").read_text(encoding="utf-8"))

    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # real, total, days
    triage_days = 0
    if rej_dir.exists():
        for d in _dates(rej_dir, since):
            if d > until:
                continue
            text = (rej_dir / f"{d}.md").read_text(encoding="utf-8")
            y = parse_yield(text)
            if y:
                triage_days += 1
            for src, (r, t) in y.items():
                agg[src][0] += r
                agg[src][1] += t
                agg[src][2] += 1

    n_days = len(days)
    n_ideas = sum(len(v) for v in per_day.values())
    zero_days = [d for d, v in per_day.items() if not v]
    lines = [f"# Pain Radar review — {since} → {until}", ""]
    lines.append(f"**{n_days} daily reports, {n_ideas} ideas, {len(zero_days)} 'nothing today' days.** "
                 f"Triage data on {triage_days} of those days.")
    lines += ["", "## Ideas by day", "", "| Date | Ideas | Titles (score) |", "|---|---|---|"]
    for d in days:
        v = per_day[d]
        t = "; ".join(f"{i['title'][:70]} ({i['total']})" for i in v) or "—"
        lines.append(f"| {d} | {len(v)} | {t} |")

    lines += ["", "## Source yield (real problems / shortlisted, per Gemini triage)", ""]
    if agg:
        lines += ["| Source | Real | Shortlisted | Days seen | Yield |", "|---|---|---|---|---|"]
        for src, (r, t, dd) in sorted(agg.items(), key=lambda kv: (-kv[1][0], -kv[1][1])):
            lines.append(f"| {src} | {r} | {t} | {dd} | {100 * r / t:.0f}% |")
        zero = [s for s, (r, t, _) in agg.items() if r == 0 and t >= 5]
        lines += ["", f"**Zero-yield sources with ≥5 shortlisted posts (cut candidates):** "
                      f"{', '.join(zero) if zero else 'none'}"]
    else:
        lines.append("No triage data found (reports/rejected/ empty) - the triage call "
                     "may be failing. Check the Stage 3 logs for `[triage] skipped`.")

    lines += ["", "## Checklist — work through with real numbers, then decide", "",
              "1. **Volume:** is ideas/day still ~1? Any 'nothing today' streaks? "
              "(Zero days are fine; padding is not.)",
              "2. **Quality:** read the ideas above. Would you actually build any? "
              "Which is the best, and how many sources/posts backed it?",
              "3. **Sources:** cut zero-yield sources above; is any source doing most of the work? "
              "Do your industries (toys, fashion, automotive, asia, trading) appear at all?",
              "4. **Rejections:** read reports/rejected/*.md - are `near_user_industries` / "
              "`buildable` cuts throwing out things you'd want? Should `user_industries` change?",
              "5. **Noise:** repeated ideas across days? Triage disagreeing with the report? "
              "(Verdicts are temperature-0 but still a rough lens.)",
              "6. **Act on evidence only:** any change to sources/thresholds needs a number from "
              "this page, not a hunch. Don't re-tune min_total_score off two weeks of one-idea days.",
              "7. **Delivery:** did Telegram arrive every day, and did the scheduled (not manual) "
              "runs produce the report? (Actions tab: event = schedule.)"]
    full = "\n".join(lines) + "\n"

    short = [f"📋 Pain Radar 2-week review ({since} → {until})",
             f"{n_days} reports · {n_ideas} ideas · {len(zero_days)} empty days"]
    if agg:
        top = sorted(agg.items(), key=lambda kv: -kv[1][0])[:3]
        short.append("Top sources: " + ", ".join(f"{s} {r}/{t}" for s, (r, t, _) in top))
    short.append("Full digest + checklist: reports/review-" + until + ".md in the repo.")
    return full, "\n".join(short)
