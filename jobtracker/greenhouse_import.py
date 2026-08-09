from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from .linkedin_import import read_csv_rows
from .url_tools import clean_url
from .utils import json_default, normalize_name, normalize_space, sha256_text

DEFAULT_TRACKING_DIR = Path("Docs/Tracking")
DEFAULT_GREENHOUSE_CSV = DEFAULT_TRACKING_DIR / "greenhouse.csv"


@dataclass(frozen=True)
class GreenhouseApplicationRecord:
    row_number: int
    source_file: str
    raw_row: dict[str, str]
    external_id: str
    greenhouse_application_id: str | None
    company: str
    title: str
    application_url: str | None
    location: str | None
    work_model: str | None
    applied_at: date | None
    source_status: str | None
    status: str
    current_stage: str
    outcome: str | None
    decline_reason: str | None
    extra_info: str | None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=json_default)


def _default_path(path: str | Path | None, default_path: Path) -> Path | None:
    if path is None:
        return default_path if default_path.exists() else None
    resolved = Path(path)
    return resolved if resolved.exists() else None


def _clean_optional(value: str | None) -> str | None:
    text = normalize_space(value)
    if not text or text.startswith("["):
        return None
    return text


def greenhouse_application_id_from_url(value: str | None) -> str | None:
    text = normalize_space(value)
    if not text:
        return None
    match = re.search(r"/applications/(\d+)", text)
    return match.group(1) if match else None


def _parse_applied_approx(value: str | None, as_of: date) -> date | None:
    from .linkedin_import import parse_applied_approx

    return parse_applied_approx(value, as_of)


def _application_status_from_posting_status(
    posting_status: str | None, extra_info: str | None
) -> tuple[str, str, str | None, str | None]:
    status_text = normalize_space(posting_status)
    normalized = normalize_name(status_text)
    info = normalize_space(extra_info)
    if normalized in {"inactive", "closed", "archived"} or "inactive" in normalized:
        return "declined", "Declined", "declined", info or "Inactive in Greenhouse"
    if normalized in {"active", "open"}:
        return "applied", "Applied", None, None
    if normalized:
        return normalized.replace(" ", "_"), status_text, None, None
    return "applied", "Applied", None, None


def build_greenhouse_application_records(
    path: str | Path | None = None,
    as_of: date | None = None,
) -> tuple[list[GreenhouseApplicationRecord], list[dict[str, Any]]]:
    csv_path = _default_path(path, DEFAULT_GREENHOUSE_CSV)
    if not csv_path:
        return [], []

    anchor = as_of or date.today()
    _fields, rows = read_csv_rows(csv_path)
    records: list[GreenhouseApplicationRecord] = []
    skipped: list[dict[str, Any]] = []

    for row_number, row in enumerate(rows, start=2):
        company = normalize_space(row.get("company"))
        title = normalize_space(row.get("role") or row.get("role_title") or row.get("title"))
        if not company or not title:
            skipped.append(
                {
                    "source_file": str(csv_path),
                    "row_number": row_number,
                    "reason": "missing_company_or_title",
                    "row": row,
                }
            )
            continue

        application_url = clean_url(row.get("application_link"))
        application_id = greenhouse_application_id_from_url(application_url or row.get("application_link"))
        external_id = (
            f"application:{application_id}"
            if application_id
            else sha256_text(f"{csv_path}|{row_number}|{company}|{title}")[:16]
        )
        extra_info = _clean_optional(row.get("extra_info"))
        status, current_stage, outcome, decline_reason = _application_status_from_posting_status(
            row.get("posting_status"), extra_info
        )

        records.append(
            GreenhouseApplicationRecord(
                row_number=row_number,
                source_file=str(csv_path),
                raw_row=row,
                external_id=external_id,
                greenhouse_application_id=application_id,
                company=company,
                title=title,
                application_url=application_url,
                location=_clean_optional(row.get("location")),
                work_model=_clean_optional(row.get("work_model")),
                applied_at=_parse_applied_approx(row.get("applied_approx"), anchor),
                source_status=normalize_space(row.get("posting_status")).lower() or None,
                status=status,
                current_stage=current_stage,
                outcome=outcome,
                decline_reason=decline_reason,
                extra_info=extra_info,
            )
        )

    return records, skipped


def summarize_greenhouse_tracking(
    path: str | Path | None = None, as_of: date | None = None
) -> dict[str, Any]:
    records, skipped = build_greenhouse_application_records(path, as_of=as_of)
    source_statuses = Counter(record.source_status or "[blank]" for record in records)
    application_statuses = Counter(record.status for record in records)
    return {
        "application_rows": len(records),
        "active_rows": source_statuses.get("active", 0),
        "inactive_rows": source_statuses.get("inactive", 0),
        "declined_from_inactive_rows": sum(
            1 for record in records if record.source_status == "inactive" and record.status == "declined"
        ),
        "linked_rows": sum(1 for record in records if record.application_url),
        "rows_with_greenhouse_application_id": sum(
            1 for record in records if record.greenhouse_application_id
        ),
        "source_statuses": dict(source_statuses),
        "application_statuses": dict(application_statuses),
        "skipped_rows": len(skipped),
        "skipped": skipped,
    }


def _provider(conn: Any) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into providers(slug, name, provider_type, website_url)
            values ('greenhouse', 'Greenhouse', 'ats', 'https://www.greenhouse.com/')
            on conflict(slug) do update set
              name = excluded.name,
              provider_type = excluded.provider_type,
              website_url = excluded.website_url,
              updated_at = now()
            returning id
            """
        )
        return cur.fetchone()["id"]


def _organization(conn: Any, company: str, metadata: dict[str, Any]) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into organizations(name, normalized_name, metadata)
            values (%s, %s, %s::jsonb)
            on conflict(normalized_name) do update set
              metadata = organizations.metadata || excluded.metadata,
              updated_at = now()
            returning id
            """,
            (company, normalize_name(company), _json({"greenhouse_import": metadata})),
        )
        return cur.fetchone()["id"]


def _find_existing_opportunity(
    conn: Any,
    provider_id: str,
    organization_id: str,
    title: str,
    external_id: str | None,
    source_url: str | None,
    location: str | None,
) -> str | None:
    with conn.cursor() as cur:
        if external_id:
            cur.execute(
                "select id from opportunities where provider_id = %s and external_id = %s",
                (provider_id, external_id),
            )
            row = cur.fetchone()
            if row:
                return row["id"]
        if source_url:
            cur.execute(
                "select id from opportunities where provider_id = %s and source_url = %s order by created_at asc limit 1",
                (provider_id, source_url),
            )
            row = cur.fetchone()
            if row:
                return row["id"]
        cur.execute(
            """
            select id from opportunities
            where provider_id = %s
              and organization_id = %s
              and normalized_title = %s
              and location_text is not distinct from %s
            order by created_at asc
            limit 1
            """,
            (provider_id, organization_id, normalize_name(title), location),
        )
        row = cur.fetchone()
        return row["id"] if row else None


def _applied_datetime(value: date | None) -> datetime | None:
    return datetime.combine(value, time.min) if value else None


def _opportunity_metadata(record: GreenhouseApplicationRecord) -> dict[str, Any]:
    return {
        "source": "greenhouse_applications_csv",
        "source_file": record.source_file,
        "row_number": record.row_number,
        "greenhouse_application_id": record.greenhouse_application_id,
        "raw_row": record.raw_row,
    }


def _upsert_opportunity(conn: Any, provider_id: str, record: GreenhouseApplicationRecord) -> str:
    metadata = _opportunity_metadata(record)
    organization_id = _organization(conn, record.company, metadata)
    existing_id = _find_existing_opportunity(
        conn,
        provider_id,
        organization_id,
        record.title,
        record.external_id,
        record.application_url,
        record.location,
    )
    first_seen = _applied_datetime(record.applied_at)
    insert_params = (
        provider_id,
        organization_id,
        "employment",
        record.title,
        normalize_name(record.title),
        record.external_id,
        record.application_url,
        record.application_url,
        record.location,
        record.work_model,
        record.source_status,
        first_seen,
        first_seen,
        _json({"greenhouse_import": metadata}),
    )
    with conn.cursor() as cur:
        if existing_id:
            update_params = (
                provider_id,
                organization_id,
                "employment",
                record.title,
                normalize_name(record.title),
                record.external_id,
                record.application_url,
                record.application_url,
                record.location,
                record.work_model,
                record.source_status,
                first_seen,
                first_seen,
                first_seen,
                _json({"greenhouse_import": metadata}),
                existing_id,
            )
            cur.execute(
                """
                update opportunities set
                  provider_id = %s,
                  organization_id = %s,
                  opportunity_type = %s,
                  title = %s,
                  normalized_title = %s,
                  external_id = coalesce(%s, external_id),
                  source_url = coalesce(%s, source_url),
                  apply_url = coalesce(%s, apply_url),
                  location_text = coalesce(%s, location_text),
                  work_model = coalesce(%s, work_model),
                  source_status = coalesce(%s, source_status),
                  first_seen_at = coalesce(first_seen_at, %s),
                  last_seen_at = greatest(coalesce(last_seen_at, %s), coalesce(%s, now())),
                  metadata = metadata || %s::jsonb,
                  updated_at = now()
                where id = %s
                returning id
                """,
                update_params,
            )
        else:
            cur.execute(
                """
                insert into opportunities(
                  provider_id, organization_id, opportunity_type, title, normalized_title,
                  external_id, source_url, apply_url, location_text, work_model, source_status,
                  first_seen_at, last_seen_at, metadata
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                returning id
                """,
                insert_params,
            )
        return cur.fetchone()["id"]


def _upsert_source_item(
    conn: Any, provider_id: str, opportunity_id: str, record: GreenhouseApplicationRecord
) -> str:
    metadata = _opportunity_metadata(record)
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into source_items(provider_id, opportunity_id, source_type, external_id, source_url, source_timestamp, title, summary, metadata)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict(provider_id, source_type, external_id) where external_id is not null
            do update set
              opportunity_id = excluded.opportunity_id,
              source_url = coalesce(excluded.source_url, source_items.source_url),
              source_timestamp = coalesce(excluded.source_timestamp, source_items.source_timestamp),
              title = excluded.title,
              summary = excluded.summary,
              metadata = source_items.metadata || excluded.metadata,
              updated_at = now()
            returning id
            """,
            (
                provider_id,
                opportunity_id,
                "greenhouse_applications_csv_row",
                record.external_id,
                record.application_url,
                _applied_datetime(record.applied_at),
                record.title,
                f"Greenhouse application row for {record.title}",
                _json({"greenhouse_import": metadata}),
            ),
        )
        return cur.fetchone()["id"]


def _upsert_application(
    conn: Any, provider_id: str, opportunity_id: str, record: GreenhouseApplicationRecord
) -> str:
    metadata = {
        "greenhouse_import": True,
        "source_file": record.source_file,
        "row_number": record.row_number,
        "greenhouse_application_id": record.greenhouse_application_id,
        "applied_approx": normalize_space(record.raw_row.get("applied_approx")) or None,
        "applied_at_is_approximate": bool(record.raw_row.get("applied_approx")),
        "posting_status": record.source_status,
        "raw_row": record.raw_row,
    }
    notes_parts = []
    if record.source_status:
        notes_parts.append(f"Greenhouse posting status: {record.source_status}")
    if record.extra_info:
        notes_parts.append(record.extra_info)
    notes = "\n".join(notes_parts) or None
    with conn.cursor() as cur:
        cur.execute("select organization_id from opportunities where id = %s", (opportunity_id,))
        opportunity = cur.fetchone()
        organization_id = opportunity["organization_id"] if opportunity else None
        cur.execute(
            """
            select id from applications
            where provider_id = %s
              and opportunity_id = %s
              and application_channel = 'greenhouse'
            order by created_at asc
            limit 1
            """,
            (provider_id, opportunity_id),
        )
        existing = cur.fetchone()
        params = (
            opportunity_id,
            organization_id,
            provider_id,
            "greenhouse",
            record.status,
            record.current_stage,
            record.applied_at,
            record.outcome,
            record.decline_reason,
            notes,
            _json(metadata),
        )
        if existing:
            cur.execute(
                """
                update applications set
                  opportunity_id = %s,
                  organization_id = %s,
                  provider_id = %s,
                  application_channel = %s,
                  status = %s,
                  current_stage = %s,
                  applied_at = coalesce(%s, applied_at),
                  outcome = %s,
                  decline_reason = %s,
                  notes = coalesce(%s, notes),
                  metadata = metadata || %s::jsonb,
                  updated_at = now()
                where id = %s
                returning id
                """,
                (*params, existing["id"]),
            )
        else:
            cur.execute(
                """
                insert into applications(
                  opportunity_id, organization_id, provider_id, application_channel,
                  status, current_stage, applied_at, outcome, decline_reason, notes, metadata
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                returning id
                """,
                params,
            )
        return cur.fetchone()["id"]


def import_greenhouse_tracking(
    conn: Any,
    csv_path: str | Path | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    records, skipped = build_greenhouse_application_records(csv_path, as_of=as_of)
    stats = {
        "applications": len(records),
        "active_applications": sum(1 for record in records if record.source_status == "active"),
        "inactive_declined_applications": sum(
            1 for record in records if record.source_status == "inactive" and record.status == "declined"
        ),
        "skipped": len(skipped),
        "warnings": skipped,
    }
    with conn.transaction():
        provider_id = _provider(conn)
        for record in records:
            opportunity_id = _upsert_opportunity(conn, provider_id, record)
            _upsert_source_item(conn, provider_id, opportunity_id, record)
            _upsert_application(conn, provider_id, opportunity_id, record)
    return stats
