from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape
from typing import Any

from ...utils import normalize_space
from ..base import AlertParser


_JOB_CARD_RE = re.compile(
    r"(?:^|\s)-{5,}\s+(?P<title>[^:]{3,220}?):\s*"
    r"(?P<url>https://www\.upwork\.com/jobs/~(?P<external_id>[A-Za-z0-9]+)[^\s]*)",
    re.IGNORECASE,
)
_BUDGET_RE = re.compile(r"\b(?P<kind>Hourly|Fixed):\s*(?P<value>[^·]+)", re.IGNORECASE)
_ESTIMATED_TIME_RE = re.compile(r"Est\.\s*time:\s*(?P<value>[^·]+)", re.IGNORECASE)
_POSTED_SNIPPET_RE = re.compile(
    r"Posted\s+(?P<posted>[A-Za-z]{3},\s+[A-Za-z]{3}\s+\d{1,2}(?:,\s+\d{4})?)\s+"
    r"(?P<snippet>.*?)\s+more:",
    re.IGNORECASE,
)
_CLIENT_ECONOMICS_RE = re.compile(
    r"(?P<value>Payment\s+(?:verified|unverified).*?)(?:\s+-{5,}\s+View job details|\s+You received this email|$)",
    re.IGNORECASE,
)
_SKILLS_RE = re.compile(r"Skills:\s*(?P<value>.*?)(?:\s+Payment\s+(?:verified|unverified)|$)", re.IGNORECASE)
_SKILL_NAME_RE = re.compile(r"(?:^|\s)(?P<name>[A-Za-z][A-Za-z0-9+/#& .-]{1,80}?):(?=\s|$)", re.IGNORECASE)

_UPWORK_ALERT_TERMS = ("job", "jobs", "saved search", "recommended", "recommendation", "invite", "invitation", "opportunity")


def parse_upwork_alert_payload(
    source_payload: dict[str, Any],
    run_key: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    timestamp = now or datetime.now(timezone.utc).isoformat()
    opportunities: list[dict[str, Any]] = []
    source_items: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen_external_ids: dict[str, dict[str, Any]] = {}

    for source in source_payload.get("source_items") or []:
        if not isinstance(source, dict):
            continue
        parsed_cards = parse_upwork_source_item(source)
        source_summary = _source_summary(source, parsed_cards)
        source_items.append(source_summary)
        if not parsed_cards:
            source_name = source_summary.get("external_id") or source_summary.get("subject") or "[unknown source]"
            blockers.append(f"No deterministic Upwork job card parsed from {source_name}")
            continue
        for card in parsed_cards:
            external_id = card["external_id"]
            if external_id in seen_external_ids:
                existing_refs = seen_external_ids[external_id].setdefault("source_items", [])
                source_ref = source_summary.get("external_id")
                if source_ref and source_ref not in existing_refs:
                    existing_refs.append(source_ref)
                continue
            opportunity = _opportunity_from_card(card, source, source_summary)
            seen_external_ids[external_id] = opportunity
            opportunities.append(opportunity)

    status = "completed" if opportunities else "partial"
    if blockers and opportunities:
        status = "partial"
    resolved_run_key = run_key or _derive_run_key(source_payload, timestamp)
    return {
        "run": {
            "run_key": resolved_run_key,
            "started_at": timestamp,
            "finished_at": timestamp,
            "status": status,
            "summary": f"Parsed {len(opportunities)} Upwork opportunities from {len(source_items)} source emails using deterministic email parsing.",
            "report_email_sent": False,
            "source_items_count": len(source_items),
            "opportunities_count": len(opportunities),
            "evaluations_count": 0,
            "manual_review_count": len(blockers),
        },
        "source_items": source_items,
        "opportunities": opportunities,
        "manual_review_blockers": blockers,
        "summary": f"{len(opportunities)} Upwork opportunities parsed; {len(blockers)} parser blockers.",
    }


def parse_upwork_source_item(source: dict[str, Any]) -> list[dict[str, Any]]:
    text = normalize_space(source.get("text") or source.get("raw_text") or source.get("summary") or "")
    if not text:
        return []
    matches = [match for match in _JOB_CARD_RE.finditer(text) if _is_real_job_card(match)]
    cards: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = text[match.end():next_start]
        title = _best_title(match.group("title"), source.get("subject"))
        budget = _budget(segment)
        estimated_time = _regex_value(_ESTIMATED_TIME_RE, segment)
        posted, snippet = _posted_and_snippet(segment)
        skills = _skills(segment)
        client_economics = _regex_value(_CLIENT_ECONOMICS_RE, segment)
        missing_fields = [
            name
            for name, value in {
                "budget": budget.get("compensation_text"),
                "estimated_time": estimated_time,
                "client_economics": client_economics,
            }.items()
            if not value
        ]
        cards.append(
            {
                "external_id": match.group("external_id"),
                "title": title,
                "title_link": match.group("url"),
                "canonical_url": _canonical_upwork_url(match.group("external_id")),
                "engagement_type": budget.get("engagement_type"),
                "budget_type": budget.get("budget_type"),
                "compensation_text": budget.get("compensation_text"),
                "estimated_time": estimated_time,
                "posted_text": posted,
                "snippet": snippet,
                "skills": skills,
                "client_economics": client_economics,
                "parser_confidence": "medium" if missing_fields else "high",
                "parser_missing_fields": missing_fields,
            }
        )
    return cards


class UpworkAlertParser(AlertParser):
    def matches(self, message: dict[str, Any]) -> bool:
        return message_matches_upwork(message)

    def parse(self, message: dict[str, Any]) -> dict[str, Any] | None:
        if not self.matches(message):
            return None
        cards = parse_upwork_source_item(message)
        if not cards:
            return None
        return {"cards": cards, "parser": "upwork_alert_parser"}


def message_matches_upwork(message: dict[str, Any]) -> bool:
    sender = _sender_email(message.get("from"))
    text = _combined_message_text(message)
    upwork_context = "upwork.com" in sender or "upwork com" in text or "upwork" in text
    alert_context = any(term in text for term in _UPWORK_ALERT_TERMS) or "www upwork com jobs" in text
    return upwork_context and alert_context


def _opportunity_from_card(card: dict[str, Any], source: dict[str, Any], source_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "external_id": card["external_id"],
        "title": card["title"],
        "company": None,
        "source_url": card["canonical_url"],
        "apply_url": card["canonical_url"],
        "source_items": [source_summary["external_id"]] if source_summary.get("external_id") else [],
        "source_status": "seen",
        "opportunity_type": "freelance_project",
        "engagement_type": card.get("engagement_type"),
        "compensation_text": card.get("compensation_text"),
        "budget_type": card.get("budget_type"),
        "domain": "mobile",
        "metadata": {
            "extraction_method": "deterministic_upwork_email_parser",
            "source_fact_scope": "email_derived",
            "page_enrichment_status": "skipped_cloudflare_by_design",
            "parser_confidence": card.get("parser_confidence"),
            "parser_missing_fields": card.get("parser_missing_fields") or [],
            "email_subject": source.get("subject"),
            "email_external_id": source.get("external_id") or source.get("message_id"),
            "title_link": card.get("title_link"),
            "estimated_time": card.get("estimated_time"),
            "posted_text": card.get("posted_text"),
            "snippet": card.get("snippet"),
            "skills": card.get("skills") or [],
            "client_economics": card.get("client_economics"),
        },
    }


def _source_summary(source: dict[str, Any], cards: list[dict[str, Any]]) -> dict[str, Any]:
    external_id = normalize_space(source.get("external_id") or source.get("message_id") or source.get("id"))
    first_card = cards[0] if cards else {}
    return {
        "source_type": normalize_space(source.get("source_type")) or "email",
        "external_id": external_id,
        "source_url": first_card.get("title_link") or normalize_space(source.get("source_url") or source.get("url")) or None,
        "timestamp": normalize_space(source.get("timestamp") or source.get("email_date") or source.get("source_timestamp")) or None,
        "subject": normalize_space(source.get("subject") or source.get("title")) or None,
        "summary": normalize_space(source.get("subject") or source.get("summary") or source.get("snippet")) or None,
        "metadata": {
            "parsed_upwork_cards": len(cards),
            "parser": "deterministic_upwork_email_parser",
        },
    }


def _is_real_job_card(match: re.Match[str]) -> bool:
    title = normalize_space(match.group("title")).lower()
    url = match.group("url")
    return title != "view job details" and ("link=title" in url or title not in {"more", "view"})


def _best_title(body_title: str, subject: Any) -> str:
    cleaned_body = _clean_title(body_title)
    subject_text = normalize_space(subject)
    subject_title = re.sub(r"^new job alert:\s*", "", subject_text, flags=re.IGNORECASE)
    cleaned_subject = _clean_title(subject_title)
    if cleaned_subject and ("..." in body_title or len(cleaned_subject) > len(cleaned_body)):
        return cleaned_subject
    return cleaned_body


def _clean_title(value: Any) -> str:
    text = normalize_space(unescape(str(value) if value is not None else ""))
    text = re.sub(r"\s+", " ", text).strip(" :-")
    return re.sub(r"\s*(?:\.{3}|…)$", "", text).strip()


def _budget(segment: str) -> dict[str, str | None]:
    match = _BUDGET_RE.search(segment)
    if not match:
        return {"engagement_type": None, "budget_type": None, "compensation_text": None}
    kind = match.group("kind").lower()
    return {
        "engagement_type": "hourly" if kind == "hourly" else "fixed",
        "budget_type": "hourly" if kind == "hourly" else "fixed",
        "compensation_text": normalize_space(f"{match.group('kind').title()}: {match.group('value')}"),
    }


def _posted_and_snippet(segment: str) -> tuple[str | None, str | None]:
    match = _POSTED_SNIPPET_RE.search(segment)
    if not match:
        return None, None
    return normalize_space(match.group("posted")), _clean_snippet(match.group("snippet"))


def _clean_snippet(value: Any) -> str | None:
    text = normalize_space(unescape(str(value) if value is not None else ""))
    text = re.sub(r"\s*(?:\.{3}|…)$", "", text).strip()
    return text or None


def _skills(segment: str) -> list[str]:
    match = _SKILLS_RE.search(segment)
    if not match:
        return []
    skills_text = re.sub(r"https://www\.upwork\.com/s/[^\s]+", "", match.group("value"))
    skills = [_clean_title(skill_match.group("name")) for skill_match in _SKILL_NAME_RE.finditer(skills_text)]
    return list(dict.fromkeys(skill for skill in skills if skill))


def _regex_value(pattern: re.Pattern[str], segment: str) -> str | None:
    match = pattern.search(segment)
    if not match:
        return None
    return normalize_space(unescape(match.group("value"))).strip(" .") or None


def _canonical_upwork_url(external_id: str) -> str:
    return f"https://www.upwork.com/jobs/~{external_id}/"


def _derive_run_key(source_payload: dict[str, Any], timestamp: str) -> str:
    run = source_payload.get("run") if isinstance(source_payload.get("run"), dict) else {}
    existing = normalize_space(run.get("run_key") or source_payload.get("run_key"))
    if existing and not existing.startswith("upwork-mail-fetch"):
        return existing
    compact = re.sub(r"[^0-9]", "", timestamp)[:12] or datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    return f"upwork-{compact}"


def _sender_email(value: str | None) -> str:
    match = re.search(r"[\w.+-]+@[\w.-]+", value or "")
    return match.group(0).lower() if match else ""


def _combined_message_text(message: dict[str, Any]) -> str:
    from ...utils import normalize_name

    links = " ".join(str(link) for link in message.get("links") or [])
    return normalize_name(
        " ".join(
            [
                str(message.get("from") or ""),
                str(message.get("subject") or ""),
                str(message.get("text") or ""),
                str(message.get("raw_text") or ""),
                links,
            ]
        )
    )
