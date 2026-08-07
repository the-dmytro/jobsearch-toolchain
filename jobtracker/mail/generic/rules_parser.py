from __future__ import annotations

import re
from typing import Any

from ...utils import normalize_name, normalize_space
from ..base import AlertParser


class RulesAlertParser:
    def __init__(self, rules: dict[str, Any]) -> None:
        self.sender_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in rules.get("sender_patterns") or []]
        self.subject_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in rules.get("subject_patterns") or []]
        self.body_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in rules.get("body_patterns") or []]
        self.link_url_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in rules.get("link_url_patterns") or []]
        self.exclude_sender_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in rules.get("exclude_sender_patterns") or []]
        self.exclude_subject_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in rules.get("exclude_subject_patterns") or []]
        self.exclude_body_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in rules.get("exclude_body_patterns") or []]

    def matches(self, message: dict[str, Any]) -> bool:
        sender = normalize_space(message.get("from"))
        subject = normalize_space(message.get("subject"))
        body = self._combined_text(message)
        if any(pattern.search(sender) for pattern in self.exclude_sender_patterns):
            return False
        if any(pattern.search(subject) for pattern in self.exclude_subject_patterns):
            return False
        if any(pattern.search(body) for pattern in self.exclude_body_patterns):
            return False
        sender_ok = not self.sender_patterns or any(pattern.search(sender) for pattern in self.sender_patterns)
        subject_ok = not self.subject_patterns or any(pattern.search(subject) for pattern in self.subject_patterns)
        body_ok = not self.body_patterns or any(pattern.search(body) for pattern in self.body_patterns)
        links_ok = not self.link_url_patterns or any(
            pattern.search(link) for link in message.get("links") or [] for pattern in self.link_url_patterns
        )
        return sender_ok and subject_ok and body_ok and links_ok

    def parse(self, message: dict[str, Any]) -> dict[str, Any] | None:
        if not self.matches(message):
            return None
        matched_links = [
            link
            for link in message.get("links") or []
            if any(pattern.search(link) for pattern in self.link_url_patterns)
        ]
        return {
            "source_type": message.get("source_type") or "email",
            "external_id": message.get("external_id") or message.get("message_id"),
            "subject": message.get("subject"),
            "timestamp": message.get("timestamp") or message.get("email_date"),
            "matched_links": matched_links,
            "parser": "rules_alert_parser",
        }

    def _combined_text(self, message: dict[str, Any]) -> str:
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
