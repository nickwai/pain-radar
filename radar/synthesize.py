"""Stage 3: turn the shortlist into ranked, scored problem ideas.

Sends the whole shortlist to Gemini in ONE call. Gemini clusters related
posts into distinct problems, judges each against the hard filter (near
your industries, buildable in two weekends, no team/capital/network-effect
blocker), and scores 1-5 on four axes. Everything after that - the weighted
total, the filter enforcement, the ranking, the cap - happens in plain
Python against config/scoring.yml, not inside the model. The model clusters
and judges; the config decides what counts and by how much.

Anti-hallucination design: Gemini is given each post's ID but NEVER its
URL. It must cite posts by ID; this module looks up the real URL itself
afterward. Any ID Gemini invents that isn't in the shortlist is dropped,
not trusted.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from typing import Any

GEMINI_URL_TMPL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "problem_one_line": {"type": "STRING"},
            "who_has_it": {"type": "STRING"},
            "current_workaround": {"type": "STRING"},
            "source_post_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
            "near_user_industries": {"type": "BOOLEAN"},
            "industry_reason": {"type": "STRING"},
            "buildable_two_weekends": {"type": "BOOLEAN"},
            "buildable_reason": {"type": "STRING"},
            "needs_team_or_capital_or_network_effect": {"type": "BOOLEAN"},
            "blocker_reason": {"type": "STRING"},
            # Sanity checks added 2026-09-26 after the Tradovate idea: its
            # first step needed an API prop-firm traders can't get, and it
            # missed tools that already do it.
            "existing_solutions": {"type": "STRING"},
            "target_user_has_access": {"type": "BOOLEAN"},
            "access_reason": {"type": "STRING"},
            "scores": {
                "type": "OBJECT",
                "properties": {
                    "frequency": {"type": "INTEGER"},
                    "anger": {"type": "INTEGER"},
                    "money_evidence": {"type": "INTEGER"},
                    "ease_to_build": {"type": "INTEGER"},
                },
                "required": ["frequency", "anger", "money_evidence", "ease_to_build"],
            },
            "first_step": {"type": "STRING"},
        },
        "required": [
            "problem_one_line", "who_has_it", "current_workaround",
            "source_post_ids", "near_user_industries", "industry_reason",
            "buildable_two_weekends", "buildable_reason",
            "needs_team_or_capital_or_network_effect", "blocker_reason",
            "existing_solutions", "target_user_has_access", "access_reason",
            "scores", "first_step",
        ],
    },
}

PROMPT_TMPL = """You find real side-project ideas by reading forum/HN posts where
someone describes a genuine problem.

YOUR INDUSTRIES (the reader can only judge ideas here - reject anything else):
{industries}

TASK:
1. Group the posts below into distinct PROBLEMS. Multiple posts can be the
   same problem (that's a stronger signal - people independently hit the
   same wall). A post with no real problem in it (a sale listing, a
   showcase, small talk) should not become a cluster at all.
2. For each problem cluster, judge honestly - be a skeptic, not a cheerleader:
   - near_user_industries: is this genuinely in or near the list above?
     A vague tech tie-in doesn't count.
   - buildable_two_weekends: could ONE person with normal skill ship a
     rough, sellable version in about two weekends? If it needs deep
     domain expertise, months of integration work, or a large dataset to
     even start, say false.
   - needs_team_or_capital_or_network_effect: true if the fix genuinely
     needs a team, a licence/certification, meaningful upfront capital, or
     only works once many people already use it (a marketplace, a social
     feature). If true here, it's disqualified regardless of the rest.
   - existing_solutions: name the tools, apps, open-source projects, or
     BUILT-IN features of the platform involved that already solve this
     fully or partly - check the platform itself first, it often already
     has the setting. "none known" only if you genuinely know of none.
     A problem an existing option already solves well is not an
     opportunity: let that lower money_evidence and anger honestly.
   - target_user_has_access: can the person in who_has_it actually get
     the API, data, or account access a first version needs - free or
     cheap, without partner approval? Platforms often lock APIs to paid
     tiers, approved vendors, or certain account types (e.g. brokers deny
     API access on prop-firm accounts). If false, the idea is dropped.
     access_reason: one line saying what access is needed and why it is
     or isn't available.
3. Score 1-5 on each (1=weak signal, 5=strong):
   - frequency: how many DIFFERENT posts/people hit this
   - anger: how frustrated do they sound (real cost/time lost, not mild "meh")
   - money_evidence: STRONGEST weight later - are they explicitly already
     paying for a tool/person to solve this badly, or naming a $ figure
     they resent? Mere annoyance with no money attached scores low here.
   - ease_to_build: how simple is a believable first version
4. source_post_ids: cite the [id] of every post that supports this cluster
   (2-3 is typical). Use the EXACT id strings given, nothing invented.
5. who_has_it: one phrase for the specific person/role, not "people".
6. current_workaround: what they do about it today (a bad tool, a person,
   manual work, nothing) - this IS the evidence for money_evidence, so be
   concrete.
7. first_step: one concrete, buildable-this-weekend suggestion. Not "build
   an MVP" - the actual first thing to build or validate. It must work
   with the access the target user really has (see above).

Return ONLY the JSON array matching the schema. If nothing here is a real
problem, return an empty array [].

POSTS:
{posts}
"""


def _format_posts(posts: list[dict]) -> str:
    lines = []
    for p in posts:
        text = (p.get("text") or "")[:600]
        lines.append(
            f"[id={p['id']}] ({p['group']}/{p['channel']}) {p['title']}\n{text}"
        )
    return "\n\n".join(lines)


def build_prompt(posts: list[dict], industries: list[str]) -> str:
    industries_txt = "\n".join(f"- {i}" for i in industries)
    return PROMPT_TMPL.format(industries=industries_txt, posts=_format_posts(posts))


def _http_post_json(url: str, payload: dict, headers: dict, timeout: int = 90) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_gemini(prompt: str, model: str, api_key: str, thinking_budget: int | None,
                retries: int = 5, temperature: float | None = 0) -> list[dict]:
    """Free-tier Gemini genuinely 503s/429s/times-out under real load - this
    isn't hypothetical, it happened repeatedly while building this. A cron
    run has no one watching it retry by hand, so this backs off for real:
    2s, 4s, 8s, 16s, 32s (~1 min total) before giving up to Groq/failure.

    thinkingConfig is OMITTED entirely when thinking_budget is None - some
    models (gemini-3.5-flash-lite, confirmed live) reject the field outright
    with a 400 INVALID_ARGUMENT, they don't just ignore it. Only pass a real
    budget for a model you've verified accepts it."""
    url = GEMINI_URL_TMPL.format(model=model) + f"?key={api_key}"
    generation_config: dict = {
        "responseMimeType": "application/json",
        "responseSchema": RESPONSE_SCHEMA,
    }
    # FIX 2026-09-26: no temperature was set, so Gemini used its default and
    # the same post flipped between runs (Tradovate cut, then 21.0; Baserow
    # ease 5, then 2). 0 = as repeatable as the model allows.
    if temperature is not None:
        generation_config["temperature"] = temperature
    if thinking_budget is not None:
        generation_config["thinkingConfig"] = {"thinkingBudget": thinking_budget}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            data = _http_post_json(url, payload, {"Content-Type": "application/json"},
                                   timeout=60)
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except urllib.error.HTTPError as exc:
            # BUG FIX: a bare HTTPError's str() is just "HTTP Error 400: Bad
            # Request" - useless for debugging. Google's actual reason lives
            # in the response BODY, which is still readable off the
            # exception object here (it hasn't been consumed yet). Print it
            # now, since a non-retryable code means this is the only chance.
            try:
                body = exc.read().decode("utf-8", errors="replace")[:1000]
            except Exception:  # noqa: BLE001 - body read is best-effort
                body = "(could not read response body)"
            print(f"[synthesize] Gemini HTTP {exc.code} body: {body}", flush=True)
            last_exc = exc
            # 503/429 are transient (model overloaded / rate limit) - worth a
            # retry. Anything else (400 bad request, 403 bad key) will never
            # succeed on retry, so fail fast instead of wasting time.
            retryable = exc.code in (503, 429)
        except (TimeoutError, urllib.error.URLError) as exc:
            last_exc = exc
            retryable = True  # server accepted the connection but never replied

        if not retryable or attempt == retries - 1:
            raise last_exc
        wait = 2 ** (attempt + 1)  # 2s, 4s, 8s, 16s, 32s
        print(f"[synthesize] Gemini {type(last_exc).__name__} "
              f"({last_exc}), retry {attempt + 1}/{retries} in {wait}s...", flush=True)
        time.sleep(wait)
    raise last_exc  # unreachable, keeps type-checkers happy


def call_groq(prompt: str, model: str, api_key: str) -> list[dict]:
    """Fallback if Gemini is down/rate-limited. Groq's JSON-mode guarantee
    is looser than Gemini's schema mode, so the prompt asks explicitly for
    a bare JSON array and the caller should still validate every field -
    validate_ideas() below does that regardless of which model produced it.
    UNTESTED against a live Groq key as of writing - no GROQ_API_KEY was
    available to verify this path end-to-end. Report an issue if it 400s.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Reply with ONLY a raw JSON array, no markdown fences, no commentary."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    data = _http_post_json(GROQ_URL, payload, headers)
    text = data["choices"][0]["message"]["content"].strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text)


def synthesize_raw(posts: list[dict], config: dict, env: dict | None = None) -> list[dict]:
    """Calls the AI. Returns its raw (unfiltered, unscored-composite) list."""
    env = env if env is not None else os.environ
    industries = config.get("user_industries", [])
    syn = config["synthesis"]
    prompt = build_prompt(posts, industries)

    gemini_key = env.get("GEMINI_API_KEY")
    model = env.get("GEMINI_MODEL", syn.get("model", "gemini-3.5-flash-lite"))
    if gemini_key:
        try:
            return call_gemini(prompt, model, gemini_key, syn.get("thinking_budget"),
                               temperature=syn.get("temperature", 0))
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError,
                json.JSONDecodeError, TimeoutError) as exc:
            print(f"[synthesize] Gemini failed ({type(exc).__name__}: {exc}), "
                  f"trying Groq fallback...", flush=True)

    groq_key = env.get("GROQ_API_KEY")
    if groq_key:
        groq_model = env.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        return call_groq(prompt, groq_model, groq_key)

    raise RuntimeError(
        "No working AI backend. GEMINI_API_KEY missing/failed and no "
        "GROQ_API_KEY set as fallback. Check .env."
    )


def validate_ideas(raw: list[Any], known_ids: set[str],
                   rejected: list[dict] | None = None) -> list[dict]:
    """Drops anything malformed or citing IDs that don't exist. The model
    is a clusterer and a judge, not a trusted data source - every fact
    that will appear in the report gets checked against real data here.

    IMPROVEMENT [2026-09-24]: `rejected`, if given, collects every dropped
    cluster with a `reject_reason`, so the daily rejected-clusters log can
    show WHY Gemini's output didn't reach the report. Behaviour unchanged."""
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        ids = [i for i in item.get("source_post_ids", []) if i in known_ids]
        if not ids:
            # every real post it cited was invented - drop the whole cluster
            if rejected is not None:
                rejected.append({**item, "reject_reason": "cited no real post ids (hallucinated sources)"})
            continue
        scores = item.get("scores") or {}
        try:
            item["scores"] = {
                "frequency": int(scores["frequency"]),
                "anger": int(scores["anger"]),
                "money_evidence": int(scores["money_evidence"]),
                "ease_to_build": int(scores["ease_to_build"]),
            }
        except (KeyError, TypeError, ValueError):
            if rejected is not None:
                rejected.append({**item, "reject_reason": "malformed scores"})
            continue
        item["source_post_ids"] = ids
        out.append(item)
    return out


def score_and_filter(ideas: list[dict], config: dict,
                     rejected: list[dict] | None = None) -> list[dict]:
    syn = config["synthesis"]
    w = syn["weights"]
    kept = []

    def _reject(idea: dict, reason: str) -> None:
        # IMPROVEMENT [2026-09-24]: record instead of silently dropping.
        if rejected is not None:
            rejected.append({**idea, "reject_reason": reason})

    for idea in ideas:
        if not idea.get("near_user_industries"):
            _reject(idea, "not near your industries")
            continue
        if not idea.get("buildable_two_weekends"):
            _reject(idea, "not buildable in two weekends")
            continue
        if idea.get("needs_team_or_capital_or_network_effect"):
            _reject(idea, "needs team / capital / network effect")
            continue
        # `is False`, not falsy: a backend that omits the field (Groq) passes.
        if idea.get("target_user_has_access") is False:
            _reject(idea, "target user can't get the access a first version needs")
            continue
        s = idea["scores"]
        total = (
            s["money_evidence"] * w["money_evidence"]
            + s["frequency"] * w["frequency"]
            + s["anger"] * w["anger"]
            + s["ease_to_build"] * w["ease_to_build"]
        )
        if total < syn["min_total_score"]:
            _reject({**idea, "total_score": round(total, 1)},
                    f"total {round(total, 1)} below min_total_score {syn['min_total_score']}")
            continue
        idea["total_score"] = round(total, 1)
        kept.append(idea)

    kept.sort(key=lambda i: i["total_score"], reverse=True)
    for idea in kept[syn["max_ideas"]:]:
        _reject(idea, f"over max_ideas cap ({syn['max_ideas']})")
    return kept[: syn["max_ideas"]]


def gate_by_triage(ideas: list[dict], triage: list[dict],
                   rejected: list[dict] | None = None) -> list[dict]:
    """FIX [2026-09-26]: the clustering call and the triage call judge posts
    independently, so a post triage called `help_question` could still be
    cited by a cluster and reach the report (09-26: Shopify billing question).
    Drop cited posts whose verdict is anything but real_problem; a cluster
    left with no posts goes to the rejected log. Posts with no verdict are
    kept, and an empty triage (call failed/disabled) gates nothing."""
    if not triage:
        return ideas
    verdict = {r["id"]: r["verdict"] for r in triage}
    out = []
    for idea in ideas:
        ids = idea["source_post_ids"]
        keep = [i for i in ids if verdict.get(i, "real_problem") == "real_problem"]
        if not keep:
            if rejected is not None:
                why = ", ".join(sorted({verdict[i] for i in ids}))
                rejected.append({**idea, "reject_reason": f"triage says not a real problem ({why})"})
            continue
        idea["source_post_ids"] = keep
        out.append(idea)
    return out


def second_pass(raw: list[Any], posts: list[dict], triage: list[dict],
                config: dict, env: dict | None = None,
                verbose: bool = True) -> list[dict]:
    """ADDED 2026-09-26: triage and clustering disagree run to run - on 09-26
    triage marked 4 posts real_problem and clustering used 1. Re-cluster ONLY
    the real_problem posts no first-pass cluster cited, with the same prompt
    and the same skeptic judgement (crowding among ~40 posts is the likely
    cause). One extra call, only when there are orphans; best-effort - a
    failure keeps the first pass. Clusters are marked second_pass=True."""
    if not triage or not config["synthesis"].get("second_pass", True):
        return []
    cited = {pid for c in raw if isinstance(c, dict)
             for pid in (c.get("source_post_ids") or [])}
    real = {r["id"] for r in triage if r["verdict"] == "real_problem"}
    orphans = [p for p in posts if p["id"] in real and p["id"] not in cited]
    if not orphans:
        return []
    try:
        raw2 = synthesize_raw(orphans, config, env)
    except Exception as exc:  # noqa: BLE001 - the first pass already worked
        print(f"  [second pass] skipped ({type(exc).__name__})", flush=True)
        return []
    raw2 = [c for c in raw2 if isinstance(c, dict)] if isinstance(raw2, list) else []
    for c in raw2:
        c["second_pass"] = True
    if verbose:
        print(f"  second pass: {len(orphans)} orphan real_problem posts -> "
              f"{len(raw2)} more clusters")
    return raw2


def synthesize(posts: list[dict], config: dict, env: dict | None = None,
               verbose: bool = True,
               rejected: list[dict] | None = None,
               triage: list[dict] | None = None,
               seen: dict[str, str] | None = None) -> list[dict]:
    if not posts:
        return []
    known_ids = {p["id"] for p in posts}
    raw = synthesize_raw(posts, config, env)
    raw = raw if isinstance(raw, list) else []
    if verbose:
        print(f"  AI returned {len(raw)} raw clusters")
    raw += second_pass(raw, posts, triage or [], config, env, verbose)
    validated = validate_ideas(raw, known_ids, rejected)
    if verbose:
        dropped = (len(raw) if isinstance(raw, list) else 0) - len(validated)
        if dropped:
            print(f"  dropped {dropped} malformed/hallucinated-source clusters")
    gated = gate_by_triage(validated, triage or [], rejected)
    if verbose and len(gated) != len(validated):
        print(f"  dropped {len(validated) - len(gated)} clusters triage marked "
              f"as not real problems")
    if seen:
        from radar.history import drop_seen_ideas
        fresh = drop_seen_ideas(gated, {p["id"]: p for p in posts}, seen, rejected)
        if verbose and len(fresh) != len(gated):
            print(f"  dropped {len(gated) - len(fresh)} clusters already in an "
                  f"earlier report")
        gated = fresh
    final = score_and_filter(gated, config, rejected)
    if verbose:
        print(f"  {len(gated)} passed validation + triage -> {len(final)} cleared "
              f"the filter + min_total_score")
    return final


# ------------------------------------------------------------------ triage
# IMPROVEMENT [2026-09-24]: most of what Gemini "rejects" is rejected INSIDE
# the clustering call (it only returns problems), so the post-filter rejected
# list can be empty even when 30 of 34 posts were discarded. This second,
# BEST-EFFORT call asks for one verdict per shortlisted post so the daily log
# can show why each was skipped and which SOURCES yield real problems.
# Never raises, never affects the report or Telegram - a failure returns [].

# paid_gig added 2026-09-26: hiring posts ("looking for an n8n freelancer")
# are the clearest money signal the radar sees, but they are work to take,
# not problems to productise - they get their own report section instead.
TRIAGE_VERDICTS = ["real_problem", "help_question", "out_of_industry",
                   "not_a_problem", "product_bug_report", "paid_gig"]

TRIAGE_SCHEMA = {
    "type": "ARRAY",
    "items": {"type": "OBJECT",
              "properties": {"id": {"type": "STRING"},
                             "verdict": {"type": "STRING", "enum": TRIAGE_VERDICTS},
                             "reason": {"type": "STRING"}},
              "required": ["id", "verdict", "reason"]},
}

TRIAGE_PROMPT = """For EACH post below, decide whether it describes a real, specific
problem someone would pay to have solved, and if not, why. The reader can only
judge ideas in these industries:
{industries}

Return a JSON array with exactly one object per post: id (the EXACT id given),
verdict, reason (max 12 words). Verdicts:
- real_problem: a specific problem a person/business has, that a third party could solve
- help_question: someone asking how to use a tool or fix their own setup
- product_bug_report: a defect in a vendor's product that only the vendor can fix
- out_of_industry: a real problem, but outside the industries above
- paid_gig: someone looking to HIRE a freelancer/expert/contractor for paid work
  (use this even if the work is in any industry; NOT for people advertising
  their own services)
- not_a_problem: news, opinion, showcase, discussion, announcement, small talk

POSTS:
{posts}
"""


def triage_posts(posts: list[dict], config: dict, env: dict | None = None) -> list[dict]:
    """One verdict per shortlisted post. Best-effort: returns [] on any failure."""
    env = env if env is not None else os.environ
    syn = config["synthesis"]
    key = env.get("GEMINI_API_KEY")
    if not posts or not key or not syn.get("triage_enabled", True):
        return []
    model = env.get("GEMINI_MODEL", syn.get("model", "gemini-3.5-flash-lite"))
    industries = "\n".join(f"- {i}" for i in config.get("user_industries", []))
    prompt = TRIAGE_PROMPT.format(industries=industries, posts=_format_posts(posts))
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"responseMimeType": "application/json",
                                    "responseSchema": TRIAGE_SCHEMA,
                                    # steadier verdicts run to run (two
                                    # untuned runs disagreed 6 vs 1 real)
                                    "temperature": 0}}
    url = GEMINI_URL_TMPL.format(model=model) + f"?key={key}"
    try:
        data = _http_post_json(url, payload, {"Content-Type": "application/json"},
                               timeout=60)
        rows = json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
    except Exception as exc:  # noqa: BLE001 - diagnostics must never break the report
        # Print only the exception TYPE: the URL (and its key) can appear in str(exc).
        print(f"[triage] skipped ({type(exc).__name__})", flush=True)
        return []
    known = {p["id"] for p in posts}
    return [r for r in rows if isinstance(r, dict) and r.get("id") in known
            and r.get("verdict") in TRIAGE_VERDICTS]
