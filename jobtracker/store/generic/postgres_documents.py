"""Documents and confirmed applications in PostgreSQL (migration 007)."""

from __future__ import annotations

import json
from typing import Any

from ...utils import json_default, normalize_name, normalize_space, slugify
from ..compact import compact_facts, excerpt, sha256_text

DOCUMENT_KINDS = (
    "report",
    "application_prep",
    "cover_letter",
    "proposal",
    "reply",
    "cv_variant",
    "company_notes",
    "interview_prep",
    "compensation_research",
    "research",
    "note",
)
DOCUMENT_STATUSES = ("draft", "final", "sent", "discarded", "archived")
_DOCUMENT_COLUMNS = (
    "id, kind, status, title, content_format, content_sha256, source_key, base_profile_sha, "
    "created_by, opportunity_id, application_id, organization_id, automation_run_id, parent_id, "
    "metadata, created_at, updated_at"
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=json_default)


def _row(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        key: (str(value) if key.endswith("id") and value is not None else value) for key, value in row.items()
    }


def find_organization(conn: Any, name: str | None) -> str | None:
    normalized = normalize_name(name)
    if not normalized:
        return None
    with conn.cursor() as cur:
        cur.execute("select id from organizations where normalized_name = %s", (normalized,))
        row = cur.fetchone()
    return str(row["id"]) if row else None


def find_document_by_sha(conn: Any, content_sha256: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            f"select {_DOCUMENT_COLUMNS} from documents where content_sha256 = %s order by updated_at desc limit 1",
            (content_sha256,),
        )
        return _row(cur.fetchone())


def put_document(
    conn: Any,
    *,
    kind: str,
    body: str,
    title: str | None = None,
    status: str = "draft",
    source_key: str | None = None,
    content_format: str = "markdown",
    organization: str | None = None,
    organization_id: str | None = None,
    opportunity_id: str | None = None,
    application_id: str | None = None,
    automation_run_id: str | None = None,
    parent_id: str | None = None,
    base_profile_sha: str | None = None,
    created_by: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kind = normalize_space(kind).lower()
    if kind not in DOCUMENT_KINDS:
        raise ValueError(f"Unsupported document kind {kind!r}. Use one of: {', '.join(DOCUMENT_KINDS)}")
    status = normalize_space(status).lower() or "draft"
    if status not in DOCUMENT_STATUSES:
        raise ValueError(
            f"Unsupported document status {status!r}. Use one of: {', '.join(DOCUMENT_STATUSES)}"
        )
    if not normalize_space(body):
        raise ValueError("Document body is empty")
    if organization and not organization_id:
        organization_id = find_organization(conn, organization)
        if not organization_id:
            raise ValueError(
                f"Organization {organization!r} is not in the database. Record the opportunity first "
                "or pass --organization-id."
            )
    digest = sha256_text(body)
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            f"""
            insert into documents(
              kind, status, title, body, content_format, content_sha256, source_key, base_profile_sha,
              created_by, opportunity_id, application_id, organization_id, automation_run_id, parent_id,
              metadata
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict(source_key) where source_key is not null do update set
              kind = excluded.kind,
              status = excluded.status,
              title = coalesce(excluded.title, documents.title),
              body = excluded.body,
              content_format = excluded.content_format,
              content_sha256 = excluded.content_sha256,
              base_profile_sha = coalesce(excluded.base_profile_sha, documents.base_profile_sha),
              created_by = coalesce(excluded.created_by, documents.created_by),
              opportunity_id = coalesce(excluded.opportunity_id, documents.opportunity_id),
              application_id = coalesce(excluded.application_id, documents.application_id),
              organization_id = coalesce(excluded.organization_id, documents.organization_id),
              automation_run_id = coalesce(excluded.automation_run_id, documents.automation_run_id),
              parent_id = coalesce(excluded.parent_id, documents.parent_id),
              metadata = documents.metadata || excluded.metadata,
              updated_at = now()
            returning {_DOCUMENT_COLUMNS}
            """,
            (
                kind,
                status,
                normalize_space(title) or None,
                body,
                content_format,
                digest,
                normalize_space(source_key) or None,
                base_profile_sha,
                created_by,
                opportunity_id,
                application_id,
                organization_id,
                automation_run_id,
                parent_id,
                _json(compact_facts(metadata or {})),
            ),
        )
        stored = _row(cur.fetchone())
    readback = get_document(conn, document_id=stored["id"])
    if not readback or readback.get("content_sha256") != digest:
        raise RuntimeError(f"Document readback failed for {stored['id']}")
    return {**stored, "verified": True}


def get_document(
    conn: Any, *, document_id: str | None = None, source_key: str | None = None, with_body: bool = False
) -> dict[str, Any] | None:
    columns = _DOCUMENT_COLUMNS + (", body" if with_body else "")
    with conn.cursor() as cur:
        if document_id:
            cur.execute(f"select {columns} from documents where id = %s", (document_id,))
        elif source_key:
            cur.execute(f"select {columns} from documents where source_key = %s", (source_key,))
        else:
            raise ValueError("document_id or source_key is required")
        return _row(cur.fetchone())


def list_documents(
    conn: Any,
    *,
    kind: str | None = None,
    status: str | None = None,
    organization: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if kind:
        clauses.append("d.kind = %s")
        params.append(normalize_space(kind).lower())
    if status:
        clauses.append("d.status = %s")
        params.append(normalize_space(status).lower())
    if organization:
        clauses.append("o.normalized_name = %s")
        params.append(normalize_name(organization))
    where = f"where {' and '.join(clauses)}" if clauses else ""
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            select d.id, d.kind, d.status, d.title, d.source_key, d.content_sha256,
                   length(d.body) as chars, o.name as organization, d.updated_at
            from documents d
            left join organizations o on o.id = d.organization_id
            {where}
            order by d.updated_at desc
            limit %s
            """,
            params,
        )
        return [_row(row) for row in cur.fetchall()]


def _find_opportunity(conn: Any, external_ids: list[str]) -> str | None:
    if not external_ids:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            select id from opportunities
            where external_id = any(%s::text[]) or external_id_aliases && %s::text[]
            order by created_at asc
            limit 1
            """,
            (external_ids, external_ids),
        )
        row = cur.fetchone()
    return str(row["id"]) if row else None


def record_application(conn: Any, record: dict[str, Any]) -> dict[str, Any]:
    """Idempotently record a confirmed application with its opportunity and events.

    Reconciles by any known external ID or alias before inserting, never creates a
    second application for the same opportunity, and skips events that already exist.
    """
    from .postgres import _insert_application, _organization, _provider, _upsert_opportunity

    if record.get("confirmed") is not True:
        raise ValueError('Refusing to record: set "confirmed": true only for applications the user submitted')
    company = normalize_space(record.get("organization") or record.get("company"))
    title = normalize_space(record.get("title"))
    if not company or not title:
        raise ValueError("organization and title are required")
    provider_slug = slugify(record.get("provider") or "manual_import")
    external_id = normalize_space(record.get("external_id")) or None
    aliases = [
        normalize_space(str(value))
        for value in [external_id, *(record.get("external_id_aliases") or [])]
        if normalize_space(str(value or ""))
    ]
    with conn.transaction():
        provider_id = _provider(conn, provider_slug)
        organization_id = _organization(conn, company)
        opportunity_id = _find_opportunity(conn, aliases)
        item = {
            "external_id": external_id,
            "external_id_aliases": aliases,
            "company": company,
            "title": title,
            "source_url": record.get("source_url"),
            "apply_url": record.get("apply_url"),
            "location": record.get("location_text") or record.get("location"),
            "work_model": record.get("work_model"),
            "seniority": record.get("seniority"),
            "compensation_text": record.get("listing_compensation_text"),
            "source_status": "applied",
            "last_seen_at": record.get("applied_at"),
        }
        if opportunity_id:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update opportunities set
                      external_id_aliases = (
                        select coalesce(array_agg(distinct alias), '{}')
                        from unnest(external_id_aliases || %s::text[]) as alias
                      ),
                      organization_id = coalesce(organization_id, %s),
                      source_status = 'applied',
                      updated_at = now()
                    where id = %s
                    """,
                    (aliases, organization_id, opportunity_id),
                )
        else:
            opportunity_id = str(_upsert_opportunity(conn, provider_id, item))
        application = {
            "application_channel": record.get("application_channel") or provider_slug,
            "status": record.get("status") or "applied",
            "current_stage": record.get("current_stage"),
            "applied_at": record.get("applied_at"),
            "salary_requested_text": record.get("salary_requested_text"),
            "notes": record.get("notes"),
            "submitted_by": record.get("submitted_by"),
            "cv": record.get("cv") or record.get("cv_file"),
            "cover_letter": record.get("cover_letter") or record.get("cover_letter_attached"),
            "evidence": record.get("evidence"),
        }
        application_id = str(_insert_application(conn, provider_id, opportunity_id, application))
        with conn.cursor() as cur:
            cur.execute(
                """
                update applications set
                  salary_requested_min = coalesce(%s, salary_requested_min),
                  salary_requested_max = coalesce(%s, salary_requested_max),
                  salary_requested_currency = coalesce(%s, salary_requested_currency)
                where id = %s
                """,
                (
                    record.get("salary_requested_min"),
                    record.get("salary_requested_max"),
                    record.get("salary_requested_currency"),
                    application_id,
                ),
            )
        events = list(record.get("events") or [])
        if not events and (record.get("status") or "applied") == "applied":
            events = [
                {
                    "event_type": "applied",
                    "event_at": record.get("applied_at"),
                    "title": f"Applied: {title}",
                    "description": record.get("evidence"),
                }
            ]
        job_text = record.get("job_text")
        stored_job_text = False
        if isinstance(job_text, str) and normalize_space(job_text):
            from .postgres import _store_opportunity_text

            stored_job_text = _store_opportunity_text(
                conn,
                opportunity_id,
                job_text,
                "application",
                normalize_space(record.get("job_text_source")) or None,
            )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update opportunities
                    set description_sha256 = coalesce(description_sha256, %s),
                        description_excerpt = coalesce(description_excerpt, %s)
                    where id = %s
                    """,
                    (sha256_text(normalize_space(job_text)), excerpt(job_text), opportunity_id),
                )
        inserted_events = 0
        for event in events:
            event_type = normalize_space(event.get("event_type"))
            if not event_type:
                raise ValueError("each event needs event_type")
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select 1 from application_events
                    where application_id = %s and event_type = %s
                      and event_at is not distinct from %s::timestamptz
                      and title is not distinct from %s
                    """,
                    (application_id, event_type, event.get("event_at"), event.get("title")),
                )
                if cur.fetchone():
                    continue
                cur.execute(
                    """
                    insert into application_events(application_id, event_type, event_at, title, description, metadata)
                    values (%s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        application_id,
                        event_type,
                        event.get("event_at"),
                        event.get("title"),
                        event.get("description"),
                        _json(compact_facts(event.get("metadata") or {})),
                    ),
                )
                inserted_events += 1
    with conn.cursor() as cur:
        cur.execute(
            """
            select a.id, a.status, a.applied_at, o.id as opportunity_id, org.name as organization,
                   (select count(*) from applications x where x.opportunity_id = o.id) as applications_for_opportunity,
                   (select count(*) from application_events e where e.application_id = a.id) as events
            from applications a
            join opportunities o on o.id = a.opportunity_id
            left join organizations org on org.id = o.organization_id
            where a.id = %s
            """,
            (application_id,),
        )
        readback = _row(cur.fetchone())
    if not readback:
        raise RuntimeError(f"Application readback failed for {application_id}")
    return {
        "application_id": application_id,
        "opportunity_id": opportunity_id,
        "inserted_events": inserted_events,
        "stored_job_text": stored_job_text,
        "readback": readback,
        "verified": True,
    }
