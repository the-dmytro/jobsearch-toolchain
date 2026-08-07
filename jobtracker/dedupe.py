from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .utils import normalize_name, normalize_space, parse_timestamp, slugify
from .validation import normalize_provider_external_id, validate_payload


_TITLE_STOPWORDS = {
    "senior",
    "sr",
    "lead",
    "principal",
    "staff",
    "middle",
    "mid",
    "junior",
    "jr",
    "software",
    "engineer",
    "engineering",
    "developer",
    "dev",
    "contractor",
    "freelancer",
    "specialist",
}


@dataclass(frozen=True)
class DedupeEntry:
    provider: str
    external_id: str | None
    company_norm: str
    title_norm: str
    title_family: frozenset[str]
    run_key: str | None
    notified_at: datetime | None
    application_status: str | None
    applied_at: date | None
    payload_path: str | None = None

    @property
    def has_application(self) -> bool:
        return bool(self.application_status or self.applied_at)


@dataclass
class DedupeDecision:
    status: str = "new"
    email_policy: str = "include_detail"
    source: str = "local_fallback_index"
    reasons: list[str] = field(default_factory=list)
    matches: list[dict[str, Any]] = field(default_factory=list)

    def to_payload_fields(self) -> dict[str, Any]:
        return {
            "dedupe_status": self.status,
            "dedupe_source": self.source,
            "email_policy": self.email_policy,
            "dedupe_reasons": self.reasons,
            "dedupe_matches": self.matches[:5],
        }


def title_family(title: str | None) -> frozenset[str]:
    tokens = [token for token in normalize_name(title).split() if token and token not in _TITLE_STOPWORDS]
    return frozenset(tokens or normalize_name(title).split())


def _parse_date(value: Any) -> date | None:
    text = normalize_space(str(value) if value is not None else "")
    if text:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
    parsed = parse_timestamp(value)
    return parsed.date() if parsed else None


def _parse_datetime(value: Any) -> datetime | None:
    text = normalize_space(str(value) if value is not None else "")
    if text:
        try:
            parsed_iso = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed_iso.tzinfo is None:
                return parsed_iso.replace(tzinfo=timezone.utc)
            return parsed_iso
        except ValueError:
            pass
    parsed = parse_timestamp(value)
    if parsed and parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _days_between(left: date | datetime, right: date | datetime) -> int:
    left_date = left.date() if isinstance(left, datetime) else left
    right_date = right.date() if isinstance(right, datetime) else right
    return abs((left_date - right_date).days)


class LocalDedupeIndex:
    def __init__(self, entries: list[DedupeEntry], now: str | datetime | None = None) -> None:
        self.entries = entries
        self.now = _parse_datetime(now) if isinstance(now, str) else now or datetime.now(timezone.utc)

    @classmethod
    def from_payload_dir(
        cls,
        payload_dir: str | Path,
        now: str | datetime | None = None,
        exclude_paths: list[str | Path] | None = None,
        exclude_run_keys: list[str] | None = None,
    ) -> "LocalDedupeIndex":
        root = Path(payload_dir)
        entries: list[DedupeEntry] = []
        if not root.exists():
            return cls(entries, now=now)
        excluded = {Path(path).resolve() for path in exclude_paths or []}
        excluded_run_keys = {normalize_space(run_key) for run_key in exclude_run_keys or [] if normalize_space(run_key)}
        for path in sorted(root.rglob("*.payload.json")):
            if path.resolve() in excluded:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            run = payload.get("run") if isinstance(payload.get("run"), dict) else {}
            run_key = normalize_space(run.get("run_key") or payload.get("run_key"))
            if run_key and run_key in excluded_run_keys:
                continue
            entries.extend(_entries_from_payload(payload, str(path)))
        return cls(entries, now=now)

    def summary(self) -> dict[str, Any]:
        applications = sum(1 for entry in self.entries if entry.has_application)
        notifications = sum(1 for entry in self.entries if entry.notified_at)
        return {
            "entries": len(self.entries),
            "applications": applications,
            "notifications": notifications,
            "providers": sorted({entry.provider for entry in self.entries if entry.provider}),
        }

    def dedupe_candidate(self, provider: str, candidate: dict[str, Any], recent_application_days: int = 180, recent_notification_days: int = 14) -> DedupeDecision:
        provider_slug = slugify(provider)
        external_id = normalize_provider_external_id(provider_slug, candidate.get("external_id") or candidate.get("source_url") or candidate.get("job_url"))
        company_norm = normalize_name(candidate.get("company") or candidate.get("organization") or candidate.get("client"))
        title_norm = normalize_name(candidate.get("title") or candidate.get("role_title") or candidate.get("job_title"))
        family = title_family(title_norm)
        exact_matches = [
            entry for entry in self.entries
            if entry.provider == provider_slug and external_id and entry.external_id == external_id
        ]
        if exact_matches:
            return _decision("exact_external_id", "suppress_detail", "exact_external_id", exact_matches)

        same_company_apps = [
            entry for entry in self.entries
            if entry.company_norm
            and entry.company_norm == company_norm
            and entry.has_application
            and entry.applied_at
            and _days_between(self.now, entry.applied_at) <= recent_application_days
            and (family & entry.title_family)
        ]
        if same_company_apps:
            return _decision("same_company_recent_application", "suppress_detail", "same_company_recent_application", same_company_apps)

        recent_notifications = [
            entry for entry in self.entries
            if entry.notified_at
            and _days_between(self.now, entry.notified_at) <= recent_notification_days
            and (
                (external_id and entry.external_id == external_id)
                or (entry.company_norm == company_norm and entry.title_norm == title_norm)
            )
        ]
        if recent_notifications:
            return _decision("recently_notified", "suppress_detail", "recently_notified", recent_notifications)

        return DedupeDecision()


def _decision(status: str, email_policy: str, reason: str, entries: list[DedupeEntry]) -> DedupeDecision:
    return DedupeDecision(
        status=status,
        email_policy=email_policy,
        reasons=[reason],
        matches=[_entry_match(entry) for entry in entries],
    )


def _entry_match(entry: DedupeEntry) -> dict[str, Any]:
    return {
        "provider": entry.provider,
        "external_id": entry.external_id,
        "company": entry.company_norm,
        "title": entry.title_norm,
        "run_key": entry.run_key,
        "notified_at": entry.notified_at.isoformat() if entry.notified_at else None,
        "application_status": entry.application_status,
        "applied_at": entry.applied_at.isoformat() if entry.applied_at else None,
        "payload_path": entry.payload_path,
    }


def _entries_from_payload(payload: dict[str, Any], payload_path: str | None = None) -> list[DedupeEntry]:
    run = payload.get("run") if isinstance(payload.get("run"), dict) else {}
    run_key = normalize_space(run.get("run_key") or payload.get("run_key")) or None
    provider = slugify((run_key or "").split("-", 1)[0]) if run_key else slugify(payload.get("provider"))
    notified_at = _parse_datetime(run.get("finished_at") or run.get("started_at")) if run.get("report_email_sent") or run.get("email_sent") else None
    entries: list[DedupeEntry] = []
    for item in payload.get("opportunities") or payload.get("jobs") or []:
        if not isinstance(item, dict):
            continue
        application = item.get("application") if isinstance(item.get("application"), dict) else {}
        title = normalize_space(item.get("title") or item.get("role_title") or item.get("job_title"))
        entries.append(
            DedupeEntry(
                provider=provider,
                external_id=normalize_provider_external_id(provider, item.get("external_id") or item.get("source_url") or item.get("job_url")),
                company_norm=normalize_name(item.get("company") or item.get("organization") or item.get("client")),
                title_norm=normalize_name(title),
                title_family=title_family(title),
                run_key=run_key,
                notified_at=notified_at,
                application_status=normalize_space(application.get("status") or application.get("current_stage")) or None,
                applied_at=_parse_date(application.get("applied_at")),
                payload_path=payload_path,
            )
        )
    return entries


def dedupe_payload(payload: dict[str, Any], provider: str, index: LocalDedupeIndex) -> dict[str, Any]:
    result = validate_payload(copy.deepcopy(payload), provider=provider).normalized
    opportunities = result.get("opportunities") or []
    for item in opportunities:
        if not isinstance(item, dict):
            continue
        decision = index.dedupe_candidate(provider, item)
        item.update(decision.to_payload_fields())
    return result


def apply_db_dedupe_matches(
    payload: dict[str, Any],
    matches_by_external_id: dict[str, list[dict[str, Any]]],
    exclude_run_keys: list[str] | None = None,
) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    excluded_run_keys = {normalize_space(run_key) for run_key in exclude_run_keys or [] if normalize_space(run_key)}
    for item in result.get("opportunities") or []:
        if not isinstance(item, dict):
            continue
        external_id = normalize_space(item.get("external_id"))
        matches = _filter_db_matches(matches_by_external_id.get(external_id) or [], excluded_run_keys)
        if not matches:
            continue
        decision = _db_decision(matches)
        item.update(decision.to_payload_fields())
    return result


def _filter_db_matches(matches: list[dict[str, Any]], excluded_run_keys: set[str]) -> list[dict[str, Any]]:
    if not excluded_run_keys:
        return matches
    return [match for match in matches if not _is_current_run_only_match(match, excluded_run_keys)]


def _is_current_run_only_match(match: dict[str, Any], excluded_run_keys: set[str]) -> bool:
    if _has_application_evidence(match):
        return False
    run_keys = _match_run_keys(match)
    return bool(run_keys) and run_keys.issubset(excluded_run_keys)


def _has_application_evidence(match: dict[str, Any]) -> bool:
    return bool(
        match.get("application_id")
        or normalize_space(match.get("application_status"))
        or normalize_space(match.get("current_stage"))
        or match.get("applied_at")
    )


def _match_run_keys(match: dict[str, Any]) -> set[str]:
    raw = match.get("automation_run_keys") or match.get("run_keys") or match.get("matched_run_keys") or []
    if isinstance(raw, str):
        values = [raw]
    else:
        values = list(raw) if isinstance(raw, (list, tuple, set)) else []
    return {normalize_space(value) for value in values if normalize_space(value)}


def _db_decision(matches: list[dict[str, Any]]) -> DedupeDecision:
    priority = [
        ("exact_external_id", "db_exact_external_id"),
        ("same_company_recent_application", "db_same_company_recent_application"),
        ("exact_company_title", "db_exact_company_title"),
    ]
    for status, reason in priority:
        selected = [match for match in matches if match.get("match_type") == status]
        if selected:
            return DedupeDecision(
                status=status,
                email_policy="suppress_detail",
                source="db",
                reasons=[reason],
                matches=selected,
            )
    return DedupeDecision(
        status="db_match",
        email_policy="suppress_detail",
        source="db",
        reasons=["db_match"],
        matches=matches,
    )
