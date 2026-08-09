from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .url_tools import clean_url
from .utils import json_default, normalize_name, normalize_space, parse_timestamp, sha256_text

DEFAULT_TRACKING_DIR = Path("Docs/Tracking")
DEFAULT_JOBS_CSV = DEFAULT_TRACKING_DIR / "linkedin_jobs.csv"
DEFAULT_ACTIVE_CSV = DEFAULT_TRACKING_DIR / "linkedin_applications_active.csv"
DEFAULT_ARCHIVED_CSV = DEFAULT_TRACKING_DIR / "linkedin_applications_archived.csv"


@dataclass(frozen=True)
class LinkedInJobRecord:
    row_number: int
    source_file: str
    raw_row: dict[str, str]
    record_id: str
    linkedin_job_id: str | None
    company: str
    title: str
    job_url: str | None
    application_url: str | None


@dataclass(frozen=True)
class LinkedInApplicationRecord:
    row_number: int
    source_file: str
    raw_row: dict[str, str]
    source_kind: str
    linkedin_job_id: str | None
    company: str
    title: str
    job_url: str | None
    applied_at: date | None
    status: str
    current_stage: str
    outcome: str | None
    decline_reason: str | None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=json_default)


def read_csv_rows(path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    csv_path = Path(path)
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def linkedin_job_id_from_url(value: str | None) -> str | None:
    text = normalize_space(value)
    if not text:
        return None
    match = re.search(r"(\d{7,})", text)
    return match.group(1) if match else None


def _parse_date(value: str | None) -> date | None:
    parsed = parse_timestamp(value)
    return parsed.date() if parsed else None


def _subtract_months(anchor: date, months: int) -> date:
    month_index = anchor.month - 1 - months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    days_in_month = [
        31,
        29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
    return date(year, month, min(anchor.day, days_in_month[month - 1]))


def parse_applied_approx(value: str | None, as_of: date) -> date | None:
    text = normalize_space(value).lower()
    if not text:
        return None
    if text in {"today", "now", "just now"}:
        return as_of
    if text in {"yesterday", "1d ago", "1 day ago"}:
        return as_of - timedelta(days=1)
    match = re.match(
        r"^(\d+)\s*(d|day|days|w|wk|wks|week|weeks|mo|month|months|y|yr|yrs|year|years)\s+ago$", text
    )
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit in {"d", "day", "days"}:
            return as_of - timedelta(days=amount)
        if unit in {"w", "wk", "wks", "week", "weeks"}:
            return as_of - timedelta(weeks=amount)
        if unit in {"mo", "month", "months"}:
            return _subtract_months(as_of, amount)
        if unit in {"y", "yr", "yrs", "year", "years"}:
            return _subtract_months(as_of, amount * 12)
    return _parse_date(text)


def _status_from_stage(stage: str | None, source_kind: str) -> tuple[str, str, str | None, str | None]:
    stage_text = normalize_space(stage)
    if source_kind == "archived" or normalize_name(stage_text) == "archived":
        return "declined", "Declined", "declined", "Archived in LinkedIn"
    normalized = normalize_name(stage_text)
    if any(word in normalized for word in ("declined", "rejected", "not moving forward")):
        return "declined", stage_text or "Declined", "declined", None
    if normalized == "offer declined":
        return "offer_declined", stage_text, "offer_declined", None
    return normalized.replace(" ", "_") or "applied", stage_text or "Applied", None, None


def _default_path(path: str | Path | None, default_path: Path) -> Path | None:
    if path is None:
        return default_path if default_path.exists() else None
    resolved = Path(path)
    return resolved if resolved.exists() else None


def build_linkedin_job_records(
    path: str | Path | None = None,
) -> tuple[list[LinkedInJobRecord], list[dict[str, Any]]]:
    csv_path = _default_path(path, DEFAULT_JOBS_CSV)
    if not csv_path:
        return [], []
    _fields, rows = read_csv_rows(csv_path)
    records: list[LinkedInJobRecord] = []
    skipped: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=2):
        company = normalize_space(row.get("company"))
        title = normalize_space(row.get("role_title") or row.get("role"))
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
        linkedin_job_id = normalize_space(row.get("linkedin_job_id")) or linkedin_job_id_from_url(
            row.get("job_url")
        )
        record_id = (
            normalize_space(row.get("record_id"))
            or sha256_text(f"{csv_path}|{row_number}|{company}|{title}")[:16]
        )
        records.append(
            LinkedInJobRecord(
                row_number=row_number,
                source_file=str(csv_path),
                raw_row=row,
                record_id=record_id,
                linkedin_job_id=linkedin_job_id,
                company=company,
                title=title,
                job_url=clean_url(row.get("job_url")),
                application_url=clean_url(row.get("application_url")) or clean_url(row.get("job_url")),
            )
        )
    return records, skipped


def build_linkedin_application_records(
    active_path: str | Path | None = None,
    archived_path: str | Path | None = None,
    as_of: date | None = None,
) -> tuple[list[LinkedInApplicationRecord], list[dict[str, Any]]]:
    anchor = as_of or date.today()
    records: list[LinkedInApplicationRecord] = []
    skipped: list[dict[str, Any]] = []
    for source_kind, path, default in (
        ("active", active_path, DEFAULT_ACTIVE_CSV),
        ("archived", archived_path, DEFAULT_ARCHIVED_CSV),
    ):
        csv_path = _default_path(path, default)
        if not csv_path:
            continue
        _fields, rows = read_csv_rows(csv_path)
        for row_number, row in enumerate(rows, start=2):
            company = normalize_space(row.get("company"))
            title = normalize_space(row.get("role") or row.get("role_title"))
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
            linkedin_job_id = linkedin_job_id_from_url(row.get("job_link") or row.get("job_url"))
            status, current_stage, outcome, default_decline_reason = _status_from_stage(
                row.get("stage"), source_kind
            )
            extra_info = normalize_space(row.get("extra_info"))
            decline_reason = extra_info or default_decline_reason if outcome == "declined" else None
            records.append(
                LinkedInApplicationRecord(
                    row_number=row_number,
                    source_file=str(csv_path),
                    raw_row=row,
                    source_kind=source_kind,
                    linkedin_job_id=linkedin_job_id,
                    company=company,
                    title=title,
                    job_url=clean_url(row.get("job_link") or row.get("job_url")),
                    applied_at=parse_applied_approx(row.get("applied_approx"), anchor),
                    status=status,
                    current_stage=current_stage,
                    outcome=outcome,
                    decline_reason=decline_reason,
                )
            )
    return records, skipped


def summarize_linkedin_tracking(
    jobs_csv: str | Path | None = None,
    active_csv: str | Path | None = None,
    archived_csv: str | Path | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    job_records, job_skipped = build_linkedin_job_records(jobs_csv)
    app_records, app_skipped = build_linkedin_application_records(active_csv, archived_csv, as_of=as_of)
    app_statuses = Counter(record.status for record in app_records)
    app_sources = Counter(record.source_kind for record in app_records)
    job_statuses = Counter(
        normalize_space(record.raw_row.get("status")) or "[blank]" for record in job_records
    )
    return {
        "jobs_rows": len(job_records),
        "application_rows": len(app_records),
        "active_application_rows": app_sources.get("active", 0),
        "archived_application_rows": app_sources.get("archived", 0),
        "declined_from_archived_rows": sum(
            1 for record in app_records if record.source_kind == "archived" and record.status == "declined"
        ),
        "linked_application_rows": sum(1 for record in app_records if record.job_url),
        "application_rows_with_linkedin_id": sum(1 for record in app_records if record.linkedin_job_id),
        "job_statuses": dict(job_statuses),
        "application_statuses": dict(app_statuses),
        "skipped_rows": len(job_skipped) + len(app_skipped),
        "skipped": job_skipped + app_skipped,
    }


def _provider(conn: Any) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into providers(slug, name, provider_type, website_url)
            values ('linkedin', 'LinkedIn', 'job_board', 'https://www.linkedin.com/jobs/')
            on conflict(slug) do update set
              name = excluded.name,
              provider_type = excluded.provider_type,
              website_url = excluded.website_url,
              updated_at = now()
            returning id
            """
        )
        return cur.fetchone()["id"]


def _organization(
    conn: Any, company: str, metadata: dict[str, Any], company_domain: str | None = None
) -> str:
    domain = normalize_space(company_domain).lower()
    domains = [domain] if domain else []
    website_url = (
        f"https://{domain}" if domain and not domain.startswith(("http://", "https://")) else domain or None
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into organizations(name, normalized_name, website_url, domains, metadata)
            values (%s, %s, %s, %s, %s::jsonb)
            on conflict(normalized_name) do update set
              website_url = coalesce(organizations.website_url, excluded.website_url),
              domains = (
                select coalesce(array_agg(distinct domain_value), '{}')
                from unnest(organizations.domains || excluded.domains) as domain_value
                where domain_value <> ''
              ),
              metadata = organizations.metadata || excluded.metadata,
              updated_at = now()
            returning id
            """,
            (company, normalize_name(company), website_url, domains, _json(metadata)),
        )
        return cur.fetchone()["id"]


def _opportunity_payload_from_job(record: LinkedInJobRecord) -> dict[str, Any]:
    row = record.raw_row
    return {
        "source": "linkedin_jobs_csv",
        "source_file": record.source_file,
        "row_number": record.row_number,
        "record_id": record.record_id,
        "raw_row": row,
    }


def _opportunity_payload_from_application(record: LinkedInApplicationRecord) -> dict[str, Any]:
    return {
        "source": "linkedin_applications_csv",
        "source_kind": record.source_kind,
        "source_file": record.source_file,
        "row_number": record.row_number,
        "raw_row": record.raw_row,
    }


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


def _upsert_opportunity(
    conn: Any,
    provider_id: str,
    company: str,
    title: str,
    source_url: str | None,
    apply_url: str | None,
    external_id: str | None,
    location: str | None,
    work_model: str | None,
    engagement_type: str | None,
    seniority: str | None,
    domain: str | None,
    source_status: str | None,
    first_seen_at: datetime | None,
    last_seen_at: datetime | None,
    metadata: dict[str, Any],
) -> str:
    organization_id = _organization(conn, company, {"linkedin_import": metadata}, company_domain=domain)
    existing_id = _find_existing_opportunity(
        conn, provider_id, organization_id, title, external_id, source_url, location
    )
    params = (
        provider_id,
        organization_id,
        "employment",
        title,
        normalize_name(title),
        external_id,
        source_url,
        apply_url or source_url,
        location,
        work_model,
        engagement_type,
        seniority,
        domain,
        source_status,
        first_seen_at,
        last_seen_at,
        _json({"linkedin_import": metadata}),
    )
    with conn.cursor() as cur:
        if existing_id:
            update_params = (
                provider_id,
                organization_id,
                "employment",
                title,
                normalize_name(title),
                external_id,
                source_url,
                apply_url or source_url,
                location,
                work_model,
                engagement_type,
                seniority,
                domain,
                source_status,
                first_seen_at,
                last_seen_at,
                last_seen_at,
                _json({"linkedin_import": metadata}),
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
                  engagement_type = coalesce(%s, engagement_type),
                  seniority = coalesce(%s, seniority),
                  domain = coalesce(%s, domain),
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
                  external_id, source_url, apply_url, location_text, work_model,
                  engagement_type, seniority, domain, source_status,
                  first_seen_at, last_seen_at, metadata
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                returning id
                """,
                params,
            )
        return cur.fetchone()["id"]


def _upsert_source_item(
    conn: Any,
    provider_id: str,
    opportunity_id: str,
    source_type: str,
    external_id: str,
    source_url: str | None,
    title: str,
    metadata: dict[str, Any],
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into source_items(provider_id, opportunity_id, source_type, external_id, source_url, title, summary, metadata)
            values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict(provider_id, source_type, external_id) where external_id is not null
            do update set
              opportunity_id = excluded.opportunity_id,
              source_url = coalesce(excluded.source_url, source_items.source_url),
              title = excluded.title,
              summary = excluded.summary,
              metadata = source_items.metadata || excluded.metadata,
              updated_at = now()
            returning id
            """,
            (
                provider_id,
                opportunity_id,
                source_type,
                external_id,
                source_url,
                title,
                f"LinkedIn tracker row for {title}",
                _json({"linkedin_import": metadata}),
            ),
        )
        return cur.fetchone()["id"]


def _upsert_evaluation(conn: Any, provider_id: str, opportunity_id: str, record: LinkedInJobRecord) -> str:
    row = record.raw_row
    metadata = {
        "linkedin_tracker_record_id": record.record_id,
        "source_file": record.source_file,
        "row_number": record.row_number,
        "raw_row": row,
    }
    score = normalize_space(row.get("score"))
    with conn.cursor() as cur:
        cur.execute(
            """
            select id from evaluations
            where provider_id = %s
              and opportunity_id = %s
              and metadata->>'linkedin_tracker_record_id' = %s
            order by created_at asc
            limit 1
            """,
            (provider_id, opportunity_id, record.record_id),
        )
        existing = cur.fetchone()
        params = (
            opportunity_id,
            provider_id,
            float(score) if score else None,
            normalize_space(row.get("confidence")) or None,
            normalize_space(row.get("recommendation")) or None,
            normalize_space(row.get("priority")) or None,
            normalize_space(row.get("status")) or None,
            normalize_space(row.get("main_match")) or None,
            normalize_space(row.get("main_risks")) or None,
            normalize_space(row.get("missing_information")) or None,
            normalize_space(row.get("positioning_angle")) or None,
            normalize_space(row.get("salary_expectation")) or None,
            normalize_space(row.get("action_next")) or None,
            normalize_space(row.get("manual_review_reason")) or None,
            _json(metadata),
        )
        if existing:
            cur.execute(
                """
                update evaluations set
                  opportunity_id = %s,
                  provider_id = %s,
                  score = %s,
                  confidence = %s,
                  recommendation = %s,
                  priority = %s,
                  verdict = %s,
                  main_match = %s,
                  main_risks = %s,
                  missing_information = %s,
                  positioning_angle = %s,
                  salary_expectation = %s,
                  action_next = %s,
                  manual_review_reason = %s,
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
                insert into evaluations(
                  opportunity_id, provider_id, score, confidence, recommendation,
                  priority, verdict, main_match, main_risks, missing_information,
                  positioning_angle, salary_expectation, action_next,
                  manual_review_reason, metadata
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                returning id
                """,
                params,
            )
        return cur.fetchone()["id"]


def _upsert_application(
    conn: Any, provider_id: str, opportunity_id: str, record: LinkedInApplicationRecord
) -> str:
    row = record.raw_row
    metadata = {
        "linkedin_tracker_import": True,
        "source_kind": record.source_kind,
        "source_file": record.source_file,
        "row_number": record.row_number,
        "applied_approx": normalize_space(row.get("applied_approx")) or None,
        "applied_at_is_approximate": bool(row.get("applied_approx")),
        "posting_status": normalize_space(row.get("posting_status")) or None,
        "raw_row": row,
    }
    notes_parts = []
    if normalize_space(row.get("posting_status")):
        notes_parts.append(f"LinkedIn posting status: {normalize_space(row.get('posting_status'))}")
    if normalize_space(row.get("extra_info")):
        notes_parts.append(normalize_space(row.get("extra_info")))
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
              and application_channel = 'linkedin'
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
            "linkedin",
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


def import_linkedin_tracking(
    conn: Any,
    jobs_csv: str | Path | None = None,
    active_csv: str | Path | None = None,
    archived_csv: str | Path | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    job_records, job_skipped = build_linkedin_job_records(jobs_csv)
    app_records, app_skipped = build_linkedin_application_records(active_csv, archived_csv, as_of=as_of)
    stats = {
        "jobs": len(job_records),
        "applications": len(app_records),
        "active_applications": sum(1 for record in app_records if record.source_kind == "active"),
        "archived_declined_applications": sum(
            1 for record in app_records if record.source_kind == "archived" and record.status == "declined"
        ),
        "evaluations": 0,
        "skipped": len(job_skipped) + len(app_skipped),
        "warnings": job_skipped + app_skipped,
    }
    with conn.transaction():
        provider_id = _provider(conn)
        for record in job_records:
            row = record.raw_row
            opportunity_id = _upsert_opportunity(
                conn,
                provider_id,
                record.company,
                record.title,
                record.job_url,
                record.application_url,
                record.linkedin_job_id,
                normalize_space(row.get("location")) or None,
                normalize_space(row.get("work_model")) or None,
                normalize_space(row.get("employment_type")) or None,
                normalize_space(row.get("seniority")) or None,
                normalize_space(row.get("company_domain")) or None,
                normalize_space(row.get("source_status")) or normalize_space(row.get("status")) or None,
                parse_timestamp(row.get("first_seen")),
                parse_timestamp(row.get("last_seen")),
                _opportunity_payload_from_job(record),
            )
            _upsert_source_item(
                conn,
                provider_id,
                opportunity_id,
                "linkedin_jobs_csv_row",
                record.record_id,
                record.job_url,
                record.title,
                _opportunity_payload_from_job(record),
            )
            _upsert_evaluation(conn, provider_id, opportunity_id, record)
            stats["evaluations"] += 1

        for record in app_records:
            row = record.raw_row
            source_status = normalize_space(row.get("posting_status")).lower() or None
            opportunity_id = _upsert_opportunity(
                conn,
                provider_id,
                record.company,
                record.title,
                record.job_url,
                record.job_url,
                record.linkedin_job_id,
                normalize_space(row.get("location")) or None,
                normalize_space(row.get("work_model")) or None,
                None,
                None,
                None,
                source_status,
                None,
                None,
                _opportunity_payload_from_application(record),
            )
            source_key = (
                record.linkedin_job_id
                or sha256_text(f"{record.source_file}|{record.row_number}|{record.company}|{record.title}")[
                    :16
                ]
            )
            _upsert_source_item(
                conn,
                provider_id,
                opportunity_id,
                "linkedin_applications_csv_row",
                source_key,
                record.job_url,
                record.title,
                _opportunity_payload_from_application(record),
            )
            _upsert_application(conn, provider_id, opportunity_id, record)
    return stats
