"""Repeated paid jobs (added 2026-10-08, review item #5).

A hiring post is the strongest money signal the radar sees: someone is
paying for this work today. One post is a gig to take; the SAME task paid
for by different people is a job a template, tool or service could do
instead. The daily run saves paid_gig posts to data/gigs/DATE.json; the
weekly run groups the window's gigs by the concrete task and reports tasks paid
for by `gigs.min_repeat`+ different payers.

Gemini groups and judges; Python enforces: ids must be real gig ids, at
least min_repeat of them and of distinct payers, and task_specific must be true ("hire an n8n
freelancer" twice is a platform, not a task). Not scored and not
competitor-checked - a lead to read, not an idea. Best-effort: a failure
returns [] and the weekly report says so.
"""
from __future__ import annotations

import os

from radar.synthesize import _format_posts, call_gemini

SCHEMA = {
    "type": "ARRAY",
    "items": {"type": "OBJECT",
              "properties": {
                  "job_one_line": {"type": "STRING"},
                  "who_pays": {"type": "STRING"},
                  "gig_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                  "task_specific": {"type": "BOOLEAN"},
                  "distinct_payers": {"type": "INTEGER"},
                  "productizable": {"type": "BOOLEAN"},
                  "product_idea": {"type": "STRING"},
                  "why": {"type": "STRING"}},
              "required": ["job_one_line", "who_pays", "gig_ids", "task_specific",
                           "distinct_payers",
                           "productizable", "product_idea", "why"]},
}

PROMPT = """Below are forum posts where someone (supposedly) offers to PAY for work.
Find work that DIFFERENT people keep paying for.

1. Ignore posts that are not someone paying for work: people selling items,
   freelancers advertising their own services, job seekers, generic monthly
   "who's hiring" threads, and staff/employment ads (a role to fill - "Head
   of", "Lead", "full-time", salary) rather than a task to get done.
2. Group the remaining posts by the CONCRETE TASK being paid for (e.g.
   "connect Shopify orders to a Google Sheet report", "build a voice agent
   that books appointments"). Same platform is NOT enough - "hire an n8n
   expert" for two unrelated projects is two different tasks.
3. Return only groups with 2 or more posts. Per group:
   - job_one_line: the task, one line
   - who_pays: the kind of business/person paying
   - gig_ids: the EXACT [id] strings of its posts, nothing invented
   - task_specific: true only if the posts really describe the same task
   - distinct_payers: how many DIFFERENT people/companies paid. The same
     company cross-posting one ad on several forums counts as 1.
   - productizable: could a template, small tool or SaaS do most of this job
     so they would not need to hire someone each time?
   - product_idea: if productizable, the one thing to build; else ""
   - why: one line on the evidence (budgets, repeat wording, urgency)
Return [] if no task repeats - that is the common, honest answer.

POSTS:
{posts}
"""


def repeated_jobs(gigs: list[dict], config: dict, env=None,
                  verbose: bool = True) -> list[dict] | None:
    """Groups of the same paid task. [] = none repeat; None = check failed/off."""
    env = env if env is not None else os.environ
    gc = config.get("gigs") or {}
    key = env.get("GEMINI_API_KEY")
    min_repeat = gc.get("min_repeat", 2)
    if not gc.get("enabled", True) or not key:
        return None
    if len(gigs) < min_repeat:
        return []
    model = env.get("GEMINI_MODEL", config["synthesis"].get("model", "gemini-3.5-flash-lite"))
    try:
        rows = call_gemini(PROMPT.format(posts=_format_posts(gigs)), model, key, None,
                           schema=SCHEMA)
    except Exception as exc:  # noqa: BLE001 - leads are a bonus, never block the report
        print(f"  [gigs] repeated-job check skipped ({type(exc).__name__})", flush=True)
        return None
    known = {g["id"] for g in gigs}
    out = []
    for r in rows if isinstance(rows, list) else []:
        # distinct_payers (2026-10-08): first dry run grouped one agency's
        # job ad cross-posted to n8n + Make as a "repeated" job.
        if not isinstance(r, dict) or not r.get("task_specific") \
                or (r.get("distinct_payers") or 0) < min_repeat:
            continue
        ids = list(dict.fromkeys(i for i in r.get("gig_ids", []) if i in known))
        if len(ids) >= min_repeat:
            out.append({**r, "gig_ids": ids})
    out.sort(key=lambda r: (not r.get("productizable"), -len(r["gig_ids"])))
    if verbose:
        print(f"  repeated paid jobs: {len(gigs)} gigs -> {len(out)} tasks paid for "
              f"{min_repeat}+ times")
    return out
