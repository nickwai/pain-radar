"""Stage 3c: send the day's ideas to Telegram as a friendly, readable message.

Separate from radar/report.py's Markdown file, which is the permanent
record (tables, full score breakdown, meant for reading on a screen).
Telegram doesn't render Markdown tables at all, and nobody wants to read
a table on their phone at 7am anyway - this is the same data, written
like a person would text it to you.

Reuses whatever Telegram bot you already have (e.g. from a trading-bot
project) - just needs its own copy of TG_TOKEN/TG_CHAT_ID in THIS
project's .env, so pain-radar stays self-contained and doesn't reach
into another project's files.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import urllib.error
import urllib.request

TELEGRAM_API_TMPL = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_CHARS = 4000  # Telegram's real cap is 4096; leave headroom

AXIS_EMOJI = {
    "money_evidence": "💰",
    "frequency": "🔁",
    "anger": "😤",
    "ease_to_build": "🛠️",
}
AXIS_LABEL = {
    "money_evidence": "Money already spent",
    "frequency": "How often it came up",
    "anger": "How angry they sound",
    "ease_to_build": "Easy to build solo",
}


def _esc(text: str) -> str:
    """Telegram HTML mode only needs &, <, > escaped - not a full HTML escape."""
    return html.escape(text or "", quote=False)


def _gig_lines(gigs: list[dict], posts_by_id: dict[str, dict]) -> list[str]:
    if not gigs:
        return []
    lines = ["💼 <b>Gigs — people offering to pay for work</b>"]
    for g in gigs:
        post = posts_by_id.get(g["id"], {})
        lines.append(f'• <a href="{_esc(post.get("url", ""))}">'
                     f'{_esc(post.get("title") or g["id"])}</a> — {_esc(g["reason"])}')
    return lines


def format_message(ideas: list[dict], posts_by_id: dict[str, dict], date: str,
                   gigs: list[dict] | None = None, period: str | None = None,
                   intro: str = "", jobs: list[dict] | None = None) -> str:
    """HTML-formatted (Telegram parse_mode=HTML), not the file Markdown.
    period: weekly report (2026-10-08), e.g. "2026-09-28 → 2026-10-12"."""
    gig_lines = _gig_lines(gigs or [], posts_by_id)
    # ADDED 2026-10-08: repeated paid jobs (radar/gigs.py), weekly only.
    for j in jobs or []:
        idea = f" → build: {j['product_idea']}" if j.get("productizable") and j.get("product_idea") else ""
        gig_lines.append(f"🔁 <b>Paid for {len(j['gig_ids'])}x:</b> {_esc(j['job_one_line'])}"
                         f" ({_esc(j['who_pays'])}){_esc(idea)}")
    title = f"week {period}" if period else date
    when = "this week" if period else "today"
    intro_txt = f"{_esc(intro)}\n" if intro else ""
    if not ideas:
        text = (
            f"🔭 <b>Pain Radar — {_esc(title)}</b>\n{intro_txt}\n"
            f"Nothing {when}. No problem cleared the bar and the competitor "
            f"check — an empty week beats an idea nobody would pay for."
        )
        return text + ("\n\n" + "\n".join(gig_lines) if gig_lines else "")

    lines = [f"🎯 <b>Pain Radar — {_esc(title)}</b>"]
    if intro:
        lines.append(_esc(intro))
    lines += [f"{len(ideas)} idea{'s' if len(ideas) != 1 else ''} cleared the bar {when}.", ""]

    for i, idea in enumerate(ideas, 1):
        s = idea["scores"]
        lines.append(f"<b>{i}. {_esc(idea['problem_one_line'])}</b>")
        lines.append(f"👤 <b>Who:</b> {_esc(idea['who_has_it'])}")
        lines.append(f"🔧 <b>Doing about it now:</b> {_esc(idea['current_workaround'])}")
        if idea.get("existing_solutions"):
            lines.append(f"🧰 <b>Already exists:</b> {_esc(idea['existing_solutions'])}")
        if idea.get("access_reason"):
            lines.append(f"🔑 <b>Access:</b> {_esc(idea['access_reason'])}")

        cc = idea.get("competitor_check")
        if cc:
            names = ", ".join(c["name"] + ("" if c.get("verified") else "*")
                              for c in cc.get("competitors", [])) or "none found"
            lines.append(f"🔍 <b>Competitors ({_esc(cc['verdict'])}):</b> {_esc(names)}"
                         + (f" — gap: {_esc(cc['gap'])}" if cc.get("gap") else ""))

        score_bits = [f"{AXIS_EMOJI[k]} {v}/5" for k, v in s.items()]
        lines.append(f"📊 {'  '.join(score_bits)}  ·  <b>total {idea['total_score']}</b>")

        for pid in idea["source_post_ids"]:
            post = posts_by_id.get(pid)
            if post:
                lines.append(f'🔗 <a href="{_esc(post["url"])}">{_esc(post["title"])}</a>')

        lines.append(f"▶️ <b>First step:</b> {_esc(idea['first_step'])}")
        lines.append("")  # blank line between ideas

    lines += gig_lines
    return "\n".join(lines).rstrip()


def format_daily_pool(date: str, pooled: list[dict], pool_size: int,
                      next_weekly: str, gigs: list[dict],
                      posts_by_id: dict[str, dict], triage_ok: bool,
                      list_posts: bool = True) -> str:
    """ADDED 2026-10-08: daily heartbeat in pool mode (+ gigs); pooled post
    titles + links since 2026-10-11."""
    if not triage_ok:
        head = "⚠️ triage failed — nothing pooled today."
    else:
        # CHANGED 2026-10-12: "N pooled (pool: M)" read as "M found, only N
        # shown" - say plainly which number is today and which is the week.
        when = ("later today" if next_weekly == date else
                dt.date.fromisoformat(next_weekly).strftime("%a %m-%d"))
        head = (f"{len(pooled)} new today · {pool_size} in this week's pool · "
                f"ideas {when}"
                + (" (competitor-checked, only the ones worth digging)." if not list_posts else "."))
    text = f"📥 <b>Pain Radar — {_esc(date)}</b>\n{_esc(head)}"
    # ADDED 2026-10-11: list today's pooled posts (title + link, no score -
    # scoring happens weekly on clusters).
    if pooled and list_posts:
        text += "\n\n" + "\n".join(
            f'• <a href="{_esc(p.get("url", ""))}">{_esc(p.get("title") or p["id"])}</a>'
            f' <i>({_esc(p.get("channel") or p.get("source", ""))})</i>'
            # ADDED 2026-10-12: triage's one-line summary (no extra AI call).
            + (f'\n  ↳ {_esc(p["triage_reason"])}' if p.get("triage_reason") else "")
            for p in pooled)
    gig_lines = _gig_lines(gigs, posts_by_id)
    return text + ("\n\n" + "\n".join(gig_lines) if gig_lines else "")


def _split_for_telegram(text: str, limit: int = MAX_MESSAGE_CHARS) -> list[str]:
    """One message per idea-block would be simplest, but a single message
    reads better for a short daily list. Only splits if genuinely too long
    (5 ideas with long text could exceed 4096) - splits on the blank-line
    idea boundaries, never mid-idea."""
    if len(text) <= limit:
        return [text]
    parts, current = [], ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > limit and current:
            parts.append(current)
            current = block
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def send(text: str, token: str, chat_id: str) -> tuple[bool, str]:
    """Returns (delivered, detail). Never raises - a failed Telegram send
    should never crash the pipeline that already wrote the real report."""
    url = TELEGRAM_API_TMPL.format(token=token)
    for i, chunk in enumerate(_split_for_telegram(text)):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if not data.get("ok"):
                return False, f"Telegram API rejected it: {data.get('description')}"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            return False, f"HTTP {exc.code}: {detail}"
        except (urllib.error.URLError, TimeoutError) as exc:
            return False, f"{type(exc).__name__}: {exc}"
    return True, f"delivered ({len(_split_for_telegram(text))} message(s))"
