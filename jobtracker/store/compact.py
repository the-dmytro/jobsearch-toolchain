"""Compact metadata and text-retention rules shared by persistent stores.

Stores keep structured columns plus a small ``facts`` object. Long free text is
replaced by a hash and length; full job texts are kept only when the retention
policy selects them (see ``keep_full_text``).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ..utils import json_default, normalize_space

HEAVY_TEXT_KEYS = frozenset(
    {
        "raw_text",
        "description",
        "description_html",
        "rss_description_html",
        "html",
        "body",
        "body_html",
        "text",
        "content",
    }
)
TEXT_RETENTION_POLICIES = ("shortlisted", "all", "none")
DEFAULT_TEXT_RETENTION = "shortlisted"
EXCERPT_CHARS = 500
FACT_STRING_LIMIT = 1000

_KEEP_PATTERN = re.compile(r"\b(apply|applied|shortlist\w*|strong|high|submit\w*)\b", re.IGNORECASE)
_NEGATION_PATTERN = re.compile(r"\b(not|no|don'?t|skip\w*|reject\w*|declin\w*|avoid)\b", re.IGNORECASE)


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def excerpt(value: str | None, limit: int = EXCERPT_CHARS) -> str | None:
    text = normalize_space(value)
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def compact_facts(value: Any, *, string_limit: int = FACT_STRING_LIMIT) -> Any:
    """Drop heavy text fields (keeping hash + length) and truncate long strings."""
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in HEAVY_TEXT_KEYS and isinstance(item, str) and item:
                result[f"{key}_sha256"] = sha256_text(item)
                result[f"{key}_chars"] = len(item)
                continue
            result[key] = compact_facts(item, string_limit=string_limit)
        return result
    if isinstance(value, list):
        return [compact_facts(item, string_limit=string_limit) for item in value]
    if isinstance(value, str) and len(value) > string_limit:
        return value[: string_limit - 1] + "…"
    return value


def without_keys(value: dict[str, Any], keys: set[str] | frozenset[str]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in keys}


def normalize_text_retention(value: Any) -> str:
    policy = normalize_space(str(value or DEFAULT_TEXT_RETENTION)).lower()
    if policy not in TEXT_RETENTION_POLICIES:
        allowed = ", ".join(TEXT_RETENTION_POLICIES)
        raise ValueError(f"store.text_retention must be one of: {allowed}")
    return policy


def keep_full_text(item: dict[str, Any], policy: str) -> str | None:
    """Return a retention reason when the opportunity's full text should be stored."""
    if policy == "all":
        return "policy_all"
    if policy == "none":
        return None
    if item.get("keep_full_text") is True:
        return "explicit"
    if item.get("application"):
        return "application"
    evaluation = item.get("evaluation") or {}
    if isinstance(evaluation, dict):
        if evaluation.get("keep_full_text") is True:
            return "explicit"
        for key in ("recommendation", "decision", "verdict", "priority", "action_next"):
            value = evaluation.get(key)
            if isinstance(value, str) and _KEEP_PATTERN.search(value) and not _NEGATION_PATTERN.search(value):
                return f"evaluation_{key}"
    return None
