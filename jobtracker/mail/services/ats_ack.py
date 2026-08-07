from __future__ import annotations

import re
from typing import Any

from ...utils import normalize_space
from ..base import AlertParser
from ..generic.rules_parser import RulesAlertParser

_ATS_ACK_RULES: dict[str, dict[str, Any]] = {
    "greenhouse": {
        "sender_patterns": [r"@(?:.*\.)?greenhouse\.io$", r"@greenhouse-mail\.io$"],
        "subject_patterns": [
            r"application received",
            r"thanks for applying",
            r"thank you for applying",
            r"your application",
        ],
        "body_patterns": [r"application", r"received", r"thank"],
        "link_url_patterns": [
            r"https?://[^/]*greenhouse\.io/",
            r"https?://job-boards\.greenhouse\.io/",
            r"https?://boards\.greenhouse\.io/",
        ],
    },
    "lever": {
        "sender_patterns": [r"@lever\.co$", r"@jobs\.lever\.co$"],
        "subject_patterns": [
            r"application received",
            r"thanks for applying",
            r"thank you for applying",
            r"your application",
        ],
        "body_patterns": [r"application", r"received", r"thank"],
        "link_url_patterns": [r"https?://[^/]*lever\.co/"],
    },
    "ashby": {
        "sender_patterns": [r"@ashbyhq\.com$"],
        "subject_patterns": [
            r"application received",
            r"thanks for applying",
            r"thank you for applying",
            r"your application",
        ],
        "body_patterns": [r"application", r"received", r"thank"],
        "link_url_patterns": [r"https?://[^/]*ashbyhq\.com/"],
    },
    "workable": {
        "sender_patterns": [r"@workablemail\.com$"],
        "subject_patterns": [
            r"application received",
            r"thanks for applying",
            r"thank you for applying",
            r"your application",
        ],
        "body_patterns": [r"application", r"received", r"thank"],
        "link_url_patterns": [r"https?://[^/]*workable\.com/"],
    },
}

_APPLICATION_ID_PATTERNS = [
    re.compile(r"application\s*(?:id|#)\s*[:#]?\s*([A-Za-z0-9_-]{4,64})", re.IGNORECASE),
    re.compile(r"/applications/(\d+)", re.IGNORECASE),
]


class AtsAckParser(AlertParser):
    def __init__(self, rules: dict[str, dict[str, Any]] | None = None) -> None:
        source_rules = rules or _ATS_ACK_RULES
        self._parsers = {name: RulesAlertParser(config) for name, config in source_rules.items()}

    def matches(self, message: dict[str, Any]) -> bool:
        return any(parser.matches(message) for parser in self._parsers.values())

    def parse(self, message: dict[str, Any]) -> dict[str, Any] | None:
        matched_provider = None
        for provider, parser in self._parsers.items():
            if parser.matches(message):
                matched_provider = provider
                break
        if not matched_provider:
            return None
        text = normalize_space(
            " ".join(
                [
                    str(message.get("subject") or ""),
                    str(message.get("text") or ""),
                    str(message.get("raw_text") or ""),
                ]
            )
        )
        application_id = None
        for pattern in _APPLICATION_ID_PATTERNS:
            match = pattern.search(text)
            if match:
                application_id = match.group(1)
                break
        if not application_id:
            for link in message.get("links") or []:
                match = re.search(r"/applications/(\d+)", link, re.IGNORECASE)
                if match:
                    application_id = match.group(1)
                    break
        return {
            "source_type": message.get("source_type") or "email",
            "external_id": message.get("external_id") or message.get("message_id"),
            "subject": message.get("subject"),
            "timestamp": message.get("timestamp") or message.get("email_date"),
            "ats_provider": matched_provider,
            "application_id": application_id,
            "parser": "ats_ack_parser",
        }
