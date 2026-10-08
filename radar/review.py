"""Two-week review digest (built 2026-09-24, first run 2026-10-08; every
second Thursday since - .github/workflows/review.yml).

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
WEEK_RE = re.compile(r"^week-(\d{4}-\d{2}-\d{2})\.md$")
# Daily report in pool mode (2026-10-08): "**3 real problems added to the pool today.**"
POOLED_RE = re.compile(r"\*\*(\d+) real problems? added to the pool today")
CUT_RE = re.compile(r"^\*\*Cut because:\*\* (.+)$", re.M)
COMP_RE = re.compile(r"^\*\*Competitor check:\*\* (\w[\w ]*?)(?: —|$)", re.M)


def _dates(folder: Path, since: str, pattern: re.Pattern = DATE_RE) -> list[str]:
    out = []
    for f in sorted(folder.glob("*.md")):
        m = pattern.match(f.name)
        if m and m.group(1) >= since:
            out.append(m.group(1))
    return out


def _cut_kind(reason: str) -> str:
    """Group cut reasons: 'money_evidence 1 below ...' -> 'money_evidence below floor'."""
    if reason.startswith("competitor check"):
        return "competitor check: " + reason.split(":", 1)[1].split("-", 1)[0].strip()
    if reason.startswith("money_evidence"):
        return "money_evidence below floor"
    if reason.startswith("total "):
        return "total below min_total_score"
    return re.sub(r" \(.*", "", reason)


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
    # ADDED 2026-10-08: pool mode - ideas come from reports/week-DATE.md,
    # daily reports carry only the pooled count.
    weeks = [d for d in _dates(reports_dir, since, WEEK_RE) if d <= until]
    per_week, verdicts, cuts = {}, defaultdict(int), defaultdict(int)
    for d in weeks:
        text = (reports_dir / f"week-{d}.md").read_text(encoding="utf-8")
        per_week[d] = parse_report(text)
        for v in COMP_RE.findall(text):
            verdicts[v] += 1
        rej = rej_dir / f"week-{d}.md"
        if rej.exists():
            for r in CUT_RE.findall(rej.read_text(encoding="utf-8")):
                cuts[_cut_kind(r)] += 1
    pooled = {}
    for d in days:
        m = POOLED_RE.search((reports_dir / f"{d}.md").read_text(encoding="utf-8"))
        if m:
            pooled[d] = int(m.group(1))
    n_week_ideas = sum(len(v) for v in per_week.values())

    lines = [f"# Pain Radar review — {since} → {until}", ""]
    lines.append(f"**{len(weeks)} weekly reports, {n_week_ideas} weekly ideas; "
                 f"{n_days} daily reports, {sum(pooled.values())} real problems pooled "
                 f"on {len(pooled)} pool-mode days.** Triage data on {triage_days} days.")
    if n_ideas:
        lines.append(f"Old daily-mode ideas in the window: {n_ideas} "
                     f"({len(zero_days)} 'nothing today' days).")
    lines += ["", "## Weekly ideas", ""]
    if weeks:
        lines += ["| Week ending | Ideas | Titles (score) |", "|---|---|---|"]
        for d in weeks:
            v = per_week[d]
            t = "; ".join(f"{i['title'][:70]} ({i['total']})" for i in v) or "—"
            lines.append(f"| {d} | {len(v)} | {t} |")
        lines += ["", "**Competitor verdicts on reported ideas:** " +
                  (", ".join(f"{n} {v}" for v, n in sorted(verdicts.items())) or "none"),
                  "**Weekly cuts by reason:** " +
                  (", ".join(f"{n} {k}" for k, n in sorted(cuts.items(), key=lambda kv: -kv[1]))
                   or "none")]
    else:
        lines.append("No weekly reports in this window (pool mode started 2026-10-08).")
    if pooled:
        lines += ["", "**Pooled per day:** " +
                  ", ".join(f"{d[5:]} {n}" for d, n in pooled.items())]
    if n_ideas:
        lines += ["", "## Ideas by day (old daily mode)", "",
                  "| Date | Ideas | Titles (score) |", "|---|---|---|"]
        for d in days:
            v = per_day[d]
            if v or d not in pooled:
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
              "1. **Volume:** real problems pooled per day, ideas per week. Empty weeks are "
              "fine; padding is not. A pool under ~10 posts/week means sources, not tuning.",
              "2. **Quality:** read the weekly ideas. Would you actually build any? Do a "
              "manual competitor check on the best one - did the automatic check agree "
              "(crowded/partial/open)? If it called a crowded idea open, tighten "
              "radar/competitors.py JUDGE_PROMPT.",
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
             f"{len(weeks)} weekly reports · {n_week_ideas} ideas · "
             f"{sum(pooled.values())} real problems pooled"]
    if verdicts or cuts:
        short.append("Competitor: " + (", ".join(f"{n} {v}" for v, n in verdicts.items()) or "-")
                     + f" · cut as crowded: {sum(n for k, n in cuts.items() if 'crowded' in k)}")
    if n_ideas:
        short.append(f"(+{n_ideas} old daily-mode ideas)")
    if agg:
        top = sorted(agg.items(), key=lambda kv: -kv[1][0])[:3]
        short.append("Top sources: " + ", ".join(f"{s} {r}/{t}" for s, (r, t, _) in top))
    short.append("Full digest + checklist: reports/review-" + until + ".md in the repo.")
    return full, "\n".join(short)
