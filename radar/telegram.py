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


def format_message(ideas: list[dict], posts_by_id: dict[str, dict], date: str) -> str:
    """HTML-formatted (Telegram parse_mode=HTML), not the file Markdown."""
    if not ideas:
        return (
            f"🔭 <b>Pain Radar — {_esc(date)}</b>\n\n"
            f"Nothing today. No problem cleared the bar this run — "
            f"quieter than usual, not a failure."
        )

    lines = [f"🎯 <b>Pain Radar — {_esc(date)}</b>",
             f"{len(ideas)} idea{'s' if len(ideas) != 1 else ''} cleared the bar today.", ""]

    for i, idea in enumerate(ideas, 1):
        s = idea["scores"]
        lines.append(f"<b>{i}. {_esc(idea['problem_one_line'])}</b>")
        lines.append(f"👤 <b>Who:</b> {_esc(idea['who_has_it'])}")
        lines.append(f"🔧 <b>Doing about it now:</b> {_esc(idea['current_workaround'])}")

        score_bits = [f"{AXIS_EMOJI[k]} {v}/5" for k, v in s.items()]
        lines.append(f"📊 {'  '.join(score_bits)}  ·  <b>total {idea['total_score']}</b>")

        for pid in idea["source_post_ids"]:
            post = posts_by_id.get(pid)
            if post:
                lines.append(f'🔗 <a href="{_esc(post["url"])}">{_esc(post["title"])}</a>')

        lines.append(f"▶️ <b>First step:</b> {_esc(idea['first_step'])}")
        lines.append("")  # blank line between ideas

    return "\n".join(lines).rstrip()


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
