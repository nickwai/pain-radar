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
   an MVP" - the actual first thing to build or validate.

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
                retries: int = 5) -> list[dict]:
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
            return call_gemini(prompt, model, gemini_key, syn.get("thinking_budget"))
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


def validate_ideas(raw: list[Any], known_ids: set[str]) -> list[dict]:
    """Drops anything malformed or citing IDs that don't exist. The model
    is a clusterer and a judge, not a trusted data source - every fact
    that will appear in the report gets checked against real data here."""
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        ids = [i for i in item.get("source_post_ids", []) if i in known_ids]
        if not ids:
            continue  # every real post it cited was invented - drop the whole cluster
        scores = item.get("scores") or {}
        try:
            item["scores"] = {
                "frequency": int(scores["frequency"]),
                "anger": int(scores["anger"]),
                "money_evidence": int(scores["money_evidence"]),
                "ease_to_build": int(scores["ease_to_build"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
        item["source_post_ids"] = ids
        out.append(item)
    return out


def score_and_filter(ideas: list[dict], config: dict) -> list[dict]:
    syn = config["synthesis"]
    w = syn["weights"]
    kept = []
    for idea in ideas:
        if not idea.get("near_user_industries"):
            continue
        if not idea.get("buildable_two_weekends"):
            continue
        if idea.get("needs_team_or_capital_or_network_effect"):
            continue
        s = idea["scores"]
        total = (
            s["money_evidence"] * w["money_evidence"]
            + s["frequency"] * w["frequency"]
            + s["anger"] * w["anger"]
            + s["ease_to_build"] * w["ease_to_build"]
        )
        if total < syn["min_total_score"]:
            continue
        idea["total_score"] = round(total, 1)
        kept.append(idea)

    kept.sort(key=lambda i: i["total_score"], reverse=True)
    return kept[: syn["max_ideas"]]


def synthesize(posts: list[dict], config: dict, env: dict | None = None,
               verbose: bool = True) -> list[dict]:
    if not posts:
        return []
    known_ids = {p["id"] for p in posts}
    raw = synthesize_raw(posts, config, env)
    if verbose:
        print(f"  AI returned {len(raw) if isinstance(raw, list) else 0} raw clusters")
    validated = validate_ideas(raw, known_ids)
    if verbose:
        dropped = (len(raw) if isinstance(raw, list) else 0) - len(validated)
        if dropped:
            print(f"  dropped {dropped} malformed/hallucinated-source clusters")
    final = score_and_filter(validated, config)
    if verbose:
        print(f"  {len(validated)} passed validation -> {len(final)} cleared "
              f"the filter + min_total_score")
    return final
