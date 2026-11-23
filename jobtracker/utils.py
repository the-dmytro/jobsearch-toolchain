from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

_SPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_space(value: str | None) -> str:
    return _SPACE_RE.sub(" ", (value or "").strip())


def normalize_name(value: str | None) -> str:
    value = normalize_space(value).lower()
    value = _NON_ALNUM_RE.sub(" ", value)
    return normalize_space(value)


def slugify(value: str | None, fallback: str = "unknown") -> str:
    normalized = normalize_name(value)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or fallback


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_legacy_date(value: str | None) -> date | None:
    text = normalize_space(value)
    if not text:
        return None
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        from dateutil import parser
    except ImportError:
        return None
    try:
        return parser.parse(text, dayfirst=True, fuzzy=True).date()
    except (ValueError, TypeError, OverflowError):
        return None


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = normalize_space(str(value) if value is not None else "")
    if not text:
        return None
    try:
        from dateutil import parser
    except ImportError:
        return None
    try:
        parsed = parser.parse(text)
    except (ValueError, TypeError, OverflowError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_money_range(value: str | None) -> dict[str, Any]:
    text = normalize_space(value)
    if not text:
        return {"text": None, "min": None, "max": None, "currency": None}

    currency = None
    if "€" in text or "eur" in text.lower():
        currency = "EUR"
    elif "$" in text or "usd" in text.lower():
        currency = "USD"

    cleaned = text.replace("\t", "").replace(",", "")
    numbers = re.findall(r"\d+(?:[ .]\d{3})*(?:\.\d+)?", cleaned)
    values: list[Decimal] = []
    for number in numbers:
        compact = number.replace(" ", "").replace(".", "")
        try:
            values.append(Decimal(compact))
        except InvalidOperation:
            continue

    min_value = values[0] if values else None
    max_value = values[1] if len(values) > 1 else min_value
    return {"text": text, "min": min_value, "max": max_value, "currency": currency}


def is_placeholder_link(value: str | None) -> bool:
    text = normalize_space(value).lower()
    if not text:
        return True
    placeholder_values = {"link", "links", "link 1", "link 2", "n/a", "na", "-"}
    if text in placeholder_values:
        return True
    return all(part.strip().lower() in placeholder_values for part in text.split(","))


def valid_url(value: str | None) -> str | None:
    text = normalize_space(value)
    if not text or is_placeholder_link(text):
        return None
    if text.startswith(("http://", "https://")):
        return text
    return None


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    return str(value)


def payload_run_key(payload: dict[str, Any]) -> str | None:
    """The ``run.run_key`` of an automation payload (or a legacy top-level ``run_key``)."""
    run = payload.get("run") if isinstance(payload, dict) else None
    key = normalize_space(run.get("run_key")) if isinstance(run, dict) else ""
    return key or normalize_space(payload.get("run_key") if isinstance(payload, dict) else None) or None
