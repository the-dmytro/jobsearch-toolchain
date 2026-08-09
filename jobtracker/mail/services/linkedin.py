from __future__ import annotations

import re
from typing import Any

from ...config import load_settings
from ...utils import normalize_name
from ..base import AlertParser

_LINKEDIN_ALERT_TERMS = (
    "job",
    "jobs",
    "job alert",
    "new jobs",
    "top job",
    "you may be a fit",
    "saved job",
    "recommended",
)
_LINKEDIN_ALERT_SENDERS = {
    "jobalerts-noreply@linkedin.com",
    "jobs-listings@linkedin.com",
    "jobs-noreply@linkedin.com",
}
_LINKEDIN_APPLICATION_TERMS = (
    "application was sent",
    "application received",
    "application submitted",
    "your application has been",
    "your application to",
    "view your application",
)


def _sender_email(value: str | None) -> str:
    match = re.search(r"[\w.+-]+@[\w.-]+", value or "")
    return match.group(0).lower() if match else ""


def _combined_message_text(message: dict[str, Any]) -> str:
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


def own_report_senders() -> set[str]:
    return set(load_settings().own_report_senders)


def is_own_report(message: dict[str, Any]) -> bool:
    sender = _sender_email(message.get("from"))
    subject = normalize_name(message.get("subject"))
    if sender in own_report_senders():
        return True
    return (
        subject.startswith("upwork job alerts")
        or subject.startswith("linkedin job triage")
        or ("job alerts" in subject and "report" in subject)
    )


def message_matches_linkedin(message: dict[str, Any]) -> bool:
    if is_own_report(message):
        return False
    sender = _sender_email(message.get("from"))
    text = _combined_message_text(message)
    security_context = any(term in text for term in ("verification code", "security alert", "password reset"))
    application_context = any(term in text for term in _LINKEDIN_APPLICATION_TERMS)
    if security_context or application_context:
        return False
    linkedin_context = "linkedin.com" in sender or "linkedin com" in text or "linkedin" in text
    allowed_sender = sender in _LINKEDIN_ALERT_SENDERS
    job_context = any(term in text for term in _LINKEDIN_ALERT_TERMS) or "linkedin com jobs" in text
    return linkedin_context and allowed_sender and job_context


class LinkedInAlertParser(AlertParser):
    def matches(self, message: dict[str, Any]) -> bool:
        return message_matches_linkedin(message)

    def parse(self, message: dict[str, Any]) -> dict[str, Any] | None:
        if not self.matches(message):
            return None
        job_links = [link for link in message.get("links") or [] if "linkedin.com/jobs/view/" in link.lower()]
        return {
            "source_type": message.get("source_type") or "email",
            "external_id": message.get("external_id") or message.get("message_id"),
            "subject": message.get("subject"),
            "timestamp": message.get("timestamp") or message.get("email_date"),
            "job_links": job_links,
            "parser": "linkedin_alert_parser",
        }
