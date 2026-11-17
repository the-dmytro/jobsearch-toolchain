"""Read calendar-related e-mail: extract ``.ics`` parts or classify text-only messages."""

from __future__ import annotations

import email
import email.message
import email.policy
import html
import re
from typing import Any

from .events import MEETING_URL, CalendarSettings, ics_to_specs

NEXT_STEPS = {
    "manual_spec": "copy the calendar event template, fill it from the text, then `calendar apply`",
    "cancel_existing": "find the event (`calendar list --grep`) and "
    "`calendar cancel --key ... --reason ... --evidence ...`",
    "reschedule": "`calendar update --key ... --start ... --evidence ...` or apply the update template",
    "reply_to_recruiter": "the sender asks for availability: no event yet; the user replies",
    "verify_existing": "reminder: check that the event exists and matches (`calendar list --grep`)",
    "none": "not calendar-related",
}


def classify_text(subject: str, body: str, settings: CalendarSettings | None = None) -> str:
    settings = settings or CalendarSettings()
    hay = f"{subject}\n{body[:2000]}"
    for name, pattern in settings.text_rules:
        if re.search(pattern, subject, re.I):
            return name
    for name, pattern in settings.text_rules:
        if re.search(pattern, hay, re.I):
            return name
    return "none"


def message_parts(msg: email.message.Message) -> tuple[str, list[str]]:
    """Return ``(body_text, unique_ics_texts)`` for a parsed message."""
    text, html_text = "", ""
    icss: list[str] = []
    seen: set[str] = set()
    for part in msg.walk():
        if part.is_multipart():
            continue
        content_type = part.get_content_type()
        filename = (part.get_filename() or "").lower()
        payload = part.get_payload(decode=True) or b""
        if not isinstance(payload, bytes):
            continue
        charset = part.get_content_charset() or "utf-8"
        if content_type in ("text/calendar", "application/ics") or filename.endswith(".ics"):
            ics = payload.decode(charset, "replace")
            if "BEGIN:VCALENDAR" not in ics.upper():  # empty parts on forwarded notices
                continue
            normalized = re.sub(r"\s+", "", ics)
            if normalized not in seen:  # the same invite inline and as an attachment
                seen.add(normalized)
                icss.append(ics)
        elif content_type == "text/plain" and not text:
            text = payload.decode(charset, "replace")
        elif content_type == "text/html" and not html_text:
            raw = payload.decode(charset, "replace")
            raw = re.sub(r"(?is)<(style|script).*?</\1>", "", raw)
            html_text = re.sub(r"[ \t]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))
    return (text or html_text), icss


def parse_message(
    raw: bytes,
    evidence: str,
    default_tz: str | None = None,
    settings: CalendarSettings | None = None,
) -> dict[str, Any]:
    settings = settings or CalendarSettings()
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    subject, sender = str(msg.get("Subject", "")), str(msg.get("From", ""))
    body, icss = message_parts(msg)
    specs: list[dict[str, Any]] = []
    for ics in icss:
        try:
            specs += ics_to_specs(ics, evidence, default_tz, settings)
        except ValueError as exc:
            specs.append({"action": "invalid", "error": str(exc)})
    out: dict[str, Any] = {
        "evidence": evidence,
        "subject": subject,
        "from": sender,
        "date": str(msg.get("Date", "")),
        "ics_parts": len(icss),
        "specs": specs,
    }
    if not icss:
        action = classify_text(subject, body, settings)
        out["suggested_action"] = action
        out["meeting_urls"] = sorted({m.group(0).rstrip(".,)>") for m in MEETING_URL.finditer(body)})
        out["text"] = re.sub(r"\n\s*\n+", "\n\n", body).strip()[:2500]
        out["next_step"] = NEXT_STEPS[action]
    return out
