"""Competitor check on ideas that cleared the bar (added 2026-10-08).

At the 10-04 manual check, 0 of the 4 reported ideas survived: the
clustering call's "Already exists" line comes from model memory and named
things vaguely or not at all. This checks each surviving idea against REAL
search results before it reaches the report:

  1. Gemini writes 3 short search queries per idea (one call, all ideas).
  2. Python searches HN "Show HN" posts (Algolia) and GitHub repositories -
     both free, no key (GitHub uses GITHUB_TOKEN when set: 30 vs 10/min).
  3. Gemini judges each idea against those results (one call, all ideas):
     crowded / partial / open, naming competitors by result id.

Why not Gemini's own Google Search grounding: tested 2026-10-08, every
model on the free tier returns 429 for the google_search tool (quota 0).
DuckDuckGo's HTML endpoint answers 202 (bot challenge). HN + GitHub miss
paid SaaS that never posted on HN (watchflow.io for the 10-04 idea), so the
model may also name tools from memory - those are shown as unverified.

Same anti-hallucination rule as synthesize.py: Gemini cites result ids,
never URLs; the URL is looked up here. Best-effort: any failure keeps the
ideas and marks the check as not run.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from radar.synthesize import call_gemini

HN_URL = "https://hn.algolia.com/api/v1/search"
GH_URL = "https://api.github.com/search/repositories"
VERDICTS = ["crowded", "partial", "open"]
COVERS = ["main_use", "part", "unrelated"]

QUERY_SCHEMA = {
    "type": "ARRAY",
    "items": {"type": "OBJECT",
              "properties": {"idea": {"type": "INTEGER"},
                             "queries": {"type": "ARRAY", "items": {"type": "STRING"}}},
              "required": ["idea", "queries"]},
}

QUERY_PROMPT = """For each problem below, write {n} short search queries (2-3 words
each - the search engines need EVERY word to match, so fewer words find more)
that would find an EXISTING product, plugin or open-source tool that already
solves it. Query 1: platform name + the core noun (e.g. "n8n monitoring",
"tradovate lockout"). Then one more platform query, and one generic query for
the job itself. Return JSON: one object per problem with its number and queries.

PROBLEMS:
{ideas}
"""

JUDGE_SCHEMA = {
    "type": "ARRAY",
    "items": {"type": "OBJECT",
              "properties": {
                  "idea": {"type": "INTEGER"},
                  "competitors": {"type": "ARRAY", "items": {
                      "type": "OBJECT",
                      "properties": {"name": {"type": "STRING"},
                                     "result_id": {"type": "STRING"},
                                     "covers": {"type": "STRING", "enum": COVERS},
                                     "note": {"type": "STRING"}},
                      "required": ["name", "result_id", "covers", "note"]}},
                  "gap": {"type": "STRING"}},
              "required": ["idea", "competitors", "gap"]},
}

JUDGE_PROMPT = """You check whether side-project ideas are already solved. Be a
skeptic: a solo builder wastes weeks on an idea that already has a good answer.

For each idea you get the problem, who has it, what the clustering step
already believed exists, and real search results (HN "Show HN" posts and
GitHub repositories) with ids like r3. Most results are unrelated noise -
ignore those.

Per idea return:
- competitors: up to 5 real options - search results, well-known products, or
  the platform's OWN built-in feature. result_id = the EXACT id of the search
  result it came from, or "" if you know it from memory (only name products
  you are sure exist; never invent one). covers, for each:
  * main_use: this person could use it TODAY for the core of the problem,
    even if it is clunky, generic, or needs some setup. A free script or a
    built-in setting that does the job counts.
  * part: it handles a real piece of the problem, or the whole problem for
    a different kind of user / platform.
  * unrelated: noise - do not list these at all.
  Judge what the option DOES, not how polished it is. "Not tamper-proof",
  "not agency-ready", "not multi-platform" do not demote main_use to part.
- gap: one line - what is left that a new tool could do, concretely. If
  nothing real is left, say so.

IDEAS:
{ideas}
"""


def _get_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "pain-radar", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search_hn(query: str, n: int) -> list[dict]:
    url = HN_URL + "?" + urllib.parse.urlencode(
        {"query": query, "tags": "show_hn", "hitsPerPage": n})
    return [{"title": h.get("title") or "",
             "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
             "where": "Show HN", "extra": f"{h.get('points') or 0} points"}
            for h in _get_json(url).get("hits", [])]


def search_github(query: str, n: int, token: str | None) -> list[dict]:
    url = GH_URL + "?" + urllib.parse.urlencode(
        {"q": query, "sort": "stars", "per_page": n})
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return [{"title": f"{r['full_name']}: {(r.get('description') or '')[:120]}",
             "url": r["html_url"], "where": "GitHub",
             "extra": f"{r.get('stargazers_count', 0)} stars"}
            for r in _get_json(url, headers).get("items", [])]


def gather(queries: list[str], n: int, env) -> list[dict]:
    """Search results for one idea, deduped by URL. A failed search is skipped."""
    token = env.get("GITHUB_TOKEN")
    pause = 2.5 if token else 6.5  # GitHub search: 30/min with token, 10 without
    out: dict[str, dict] = {}
    for q in queries:
        for fn in (search_hn, lambda q2, n2: search_github(q2, n2, token)):
            try:
                hits = fn(q, n)
                # Both APIs AND every word: a 3-word query missed the
                # tradovate-lockout repo that "tradovate lockout" finds.
                if not hits and len(q.split()) > 2:
                    time.sleep(pause)
                    hits = fn(" ".join(q.split()[:2]), n)
                for r in hits:
                    out.setdefault(r["url"], r)
            except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
                print(f"  [competitors] search failed for {q!r} ({type(exc).__name__})",
                      flush=True)
        time.sleep(pause)
    return list(out.values())


def verdict_from(comps: list[dict]) -> str:
    """FIX 2026-10-08: the model's own crowded/partial/open flipped between
    runs on identical input (CI said partial for both known-crowded test
    ideas, local said crowded) - "partial" with a reworded problem as the
    "gap" was an escape hatch. Now the model only rates each competitor and
    this rule decides: any main_use, or 2+ part = crowded; 1 part = partial."""
    main = sum(c["covers"] == "main_use" for c in comps)
    part = sum(c["covers"] == "part" for c in comps)
    if main or part >= 2:
        return "crowded"
    return "partial" if part else "open"


def _idea_line(i: int, idea: dict) -> str:
    return (f"[{i}] {idea['problem_one_line']}\n    who: {idea['who_has_it']}\n"
            f"    believed to exist: {idea.get('existing_solutions') or 'none given'}")


def check(ideas: list[dict], config: dict, env=None, verbose: bool = True,
          rejected: list[dict] | None = None) -> list[dict]:
    """Annotate each idea with idea['competitor_check'] and drop those whose
    verdict is in competitor_check.cut_verdicts (to `rejected`, with reason)."""
    env = env if env is not None else os.environ
    cc = config.get("competitor_check") or {}
    key = env.get("GEMINI_API_KEY")
    if not ideas or not cc.get("enabled", True) or not key:
        return ideas
    model = env.get("GEMINI_MODEL", config["synthesis"].get("model", "gemini-3.5-flash-lite"))
    n_q, n_r = cc.get("queries_per_idea", 3), cc.get("results_per_query", 5)
    try:
        q_rows = call_gemini(
            QUERY_PROMPT.format(n=n_q, ideas="\n".join(
                _idea_line(i, d) for i, d in enumerate(ideas, 1))),
            model, key, None, schema=QUERY_SCHEMA)
        queries = {r["idea"]: [q for q in r["queries"] if q.strip()][:n_q]
                   for r in q_rows if isinstance(r, dict)}

        results: dict[str, dict] = {}  # rid -> result
        blocks = []
        for i, idea in enumerate(ideas, 1):
            found = gather(queries.get(i, []), n_r, env)
            lines = [_idea_line(i, idea),
                     f"    searched: {'; '.join(queries.get(i, [])) or '(no queries)'}"]
            for r in found:
                rid = f"r{len(results) + 1}"
                results[rid] = r
                lines.append(f"    {rid} ({r['where']}, {r['extra']}) {r['title']}")
            if not found:
                lines.append("    (no search results)")
            blocks.append("\n".join(lines))
            idea["_queries"] = queries.get(i, [])
        if verbose:
            print(f"  competitor check: {len(results)} search results for {len(ideas)} ideas")

        rows = call_gemini(JUDGE_PROMPT.format(ideas="\n\n".join(blocks)),
                           model, key, None, schema=JUDGE_SCHEMA)
    except Exception as exc:  # noqa: BLE001 - never lose the ideas over this
        print(f"  [competitors] check skipped ({type(exc).__name__})", flush=True)
        for idea in ideas:
            idea.pop("_queries", None)
            idea["competitor_check"] = {"verdict": "not run", "competitors": [],
                                        "gap": "", "queries": []}
        return ideas

    by_idea = {r["idea"]: r for r in rows if isinstance(r, dict)}
    cut = set(cc.get("cut_verdicts", ["crowded"]))
    kept = []
    for i, idea in enumerate(ideas, 1):
        r = by_idea.get(i)
        comps = []
        for c in (r or {}).get("competitors", [])[:5]:
            if c.get("covers") not in ("main_use", "part"):
                continue
            hit = results.get((c.get("result_id") or "").strip())
            comps.append({"name": c.get("name", "?"), "note": c.get("note", ""),
                          "covers": c["covers"],
                          "url": hit["url"] if hit else "", "verified": bool(hit)})
        verdict = verdict_from(comps) if r else "not run"
        idea["competitor_check"] = {
            "verdict": verdict,
            "competitors": comps, "gap": (r or {}).get("gap", ""),
            "queries": idea.pop("_queries", [])}
        if verdict in cut:
            if rejected is not None:
                rejected.append({**idea, "reject_reason":
                                 f"competitor check: {verdict} - {r.get('gap', '')}"})
            continue
        kept.append(idea)
    if verbose:
        print(f"  competitor check: {len(ideas)} ideas -> {len(kept)} not crowded")
    return kept
