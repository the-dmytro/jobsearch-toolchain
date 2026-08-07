from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from jobtracker.utils import normalize_name, normalize_space, parse_timestamp

_MONEY_RE = re.compile(
    r"((?:EUR|USD|GBP|PLN|UAH)\s*[\d\s,.]+(?:\s*[-–]\s*(?:EUR|USD|GBP|PLN|UAH)?\s*[\d\s,.]+)?|[$€£]\s*[\d\s,.]+(?:\s*[-–]\s*[$€£]?\s*[\d\s,.]+)?|[\d\s,.]+\s*[-–]\s*[\d\s,.]+\s*(?:грн|UAH)|[\d\s,.]+\s*(?:грн|UAH))",
    re.IGNORECASE,
)


def _optional_iso(value: str | datetime | None) -> str | None:
    parsed = parse_timestamp(value)
    return parsed.isoformat() if parsed else None


def _excerpt(text: str | None, limit: int = 280) -> str | None:
    cleaned = normalize_space(text)
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _find_money_text(text: str | None) -> str | None:
    cleaned = normalize_space(text)
    if not cleaned:
        return None
    match = _MONEY_RE.search(cleaned)
    return normalize_space(match.group(1)).strip(" .,;:") if match else None


def _infer_work_model(*parts: str | None) -> str | None:
    text = normalize_space(" ".join(part or "" for part in parts)).lower()
    if not text:
        return None
    if "hybrid" in text:
        return "Hybrid"
    if any(term in text for term in ("remote", "telecommute", "віддалено", "дистанційно", "remote possible")):
        return "Remote"
    if any(term in text for term in ("onsite", "on site", "office", "офіс")):
        return "On-site"
    return None


def _infer_engagement_type(*parts: str | None) -> str | None:
    text = normalize_space(" ".join(part or "" for part in parts)).lower()
    if not text:
        return None
    if any(term in text for term in ("full time", "full-time", "повна зайнятість")):
        return "Full-time"
    if any(term in text for term in ("part time", "part-time", "часткова зайнятість")):
        return "Part-time"
    if "contract" in text:
        return "Contract"
    if any(term in text for term in ("freelance", "freelancer", "project")):
        return "Contract"
    return None


def _infer_seniority(title: str | None) -> str | None:
    text = normalize_name(title)
    if not text:
        return None
    if "team lead" in text or "tech lead" in text or text.startswith("lead "):
        return "Lead"
    if "principal" in text:
        return "Principal"
    if "staff" in text:
        return "Staff"
    if "senior" in text or text.startswith("sr "):
        return "Senior"
    if "junior" in text:
        return "Junior"
    if "mid" in text or "middle" in text:
        return "Mid"
    return None


def _matches_lane(title: str | None, lane: dict[str, Any]) -> bool:
    raw_text = normalize_space(title).lower()
    normalized_text = normalize_name(title)
    if not raw_text and not normalized_text:
        return False

    def has_term(term: str) -> bool:
        raw_term = normalize_space(term).lower()
        normalized_term = normalize_name(term)
        return bool((raw_term and raw_term in raw_text) or (normalized_term and normalized_term in normalized_text))

    includes = [item for item in lane.get("include_terms") or [] if normalize_space(item)]
    excludes = [item for item in lane.get("exclude_terms") or [] if normalize_space(item)]
    if excludes and any(has_term(term) for term in excludes):
        return False
    return any(has_term(term) for term in includes)
