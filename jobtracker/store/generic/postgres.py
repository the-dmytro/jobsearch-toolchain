from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...utils import json_default, normalize_name, normalize_space, parse_timestamp, slugify, utc_now
from ...validation import validate_payload
from ..artifacts.local import artifact_store_factory
from ..base import DuplicateMatch, UpsertResult
from ..compact import (
    compact_facts,
    excerpt,
    keep_full_text,
    normalize_text_retention,
    sha256_json,
    sha256_text,
    without_keys,
)

OPPORTUNITY_COLUMN_KEYS = frozenset(
    {
        "opportunity_type",
        "external_id",
        "provider_external_id",
        "linkedin_job_id",
        "upwork_job_id",
        "company",
        "organization",
        "client",
        "title",
        "role_title",
        "job_title",
        "source_url",
        "job_url",
        "url",
        "apply_url",
        "application_url",
        "location",
        "location_text",
        "work_model",
        "engagement_type",
        "employment_type",
        "job_type",
        "seniority",
        "domain",
        "company_domain",
        "compensation_text",
        "salary_listed",
        "budget",
        "compensation_currency",
        "currency",
        "budget_type",
        "source_status",
        "first_seen_at",
        "first_seen",
        "last_seen_at",
        "last_seen",
        "evaluation",
        "application",
        "source_items",
        "external_id_aliases",
        "requirement_tags",
        "raw_text",
        "description",
    }
)
SOURCE_ITEM_COLUMN_KEYS = frozenset(
    {
        "source_type",
        "external_id",
        "message_id",
        "id",
        "source_url",
        "url",
        "gmail_link",
        "timestamp",
        "source_timestamp",
        "email_date",
        "title",
        "subject",
        "summary",
        "snippet",
        "raw_text",
    }
)
EVALUATION_COLUMN_KEYS = frozenset(
    {
        "score",
        "confidence",
        "recommendation",
        "priority",
        "verdict",
        "main_match",
        "reason",
        "main_risks",
        "risk",
        "missing_information",
        "positioning_angle",
        "salary_expectation",
        "pricing_recommendation",
        "proposal_text",
        "action_next",
        "action",
        "manual_review_reason",
    }
)
APPLICATION_COLUMN_KEYS = frozenset(
    {
        "application_channel",
        "status",
        "current_stage",
        "stage",
        "applied_at",
        "salary_requested_text",
        "outcome",
        "decline_reason",
        "notes",
    }
)


def _text_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = normalize_space(str(item)) if item is not None else ""
        if text and text not in result:
            result.append(text)
    return result


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=json_default)


def _provider(conn: Any, slug: str) -> str:
    name = slug.replace("_", " ").replace("-", " ").title()
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into providers(slug, name)
            values (%s, %s)
            on conflict(slug) do update set updated_at = now()
            returning id
            """,
            (slug, name),
        )
        return cur.fetchone()["id"]


def _organization(conn: Any, company: str | None, metadata: dict[str, Any] | None = None) -> str | None:
    company = normalize_space(company)
    if not company:
        return None
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
            (company, normalize_name(company), _json(metadata or {})),
        )
        return cur.fetchone()["id"]


def _artifact(
    conn: Any, report_path: str | None, provider_slug: str, run_key: str, artifact_backend: str = "local"
) -> str | None:
    """Register the report with the configured artifact backend; a failed upload is an error."""
    if not report_path:
        return None
    path = Path(report_path)
    storage_path = f"{provider_slug}/{run_key}/{path.name}"
    ref = artifact_store_factory(artifact_backend).upload(path, storage_path=storage_path)
    if artifact_backend != "local" and not ref.uploaded:
        from ...db import MissingConfigurationError

        raise MissingConfigurationError(
            f"store.artifact_backend = {artifact_backend!r} but the upload did not happen: "
            f"{ref.upload_warning or 'unknown reason'}"
        )
    upload = ref.as_dict()
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into artifacts(
              artifact_type, title, storage_bucket, storage_path, local_path,
              mime_type, sha256, size_bytes, related_type, metadata
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            returning id
            """,
            (
                "automation_report",
                path.name,
                upload.get("storage_bucket"),
                upload.get("storage_path"),
                str(path),
                "text/markdown",
                upload.get("sha256"),
                upload.get("size_bytes"),
                "automation_run",
                _json(upload),
            ),
        )
        return cur.fetchone()["id"]


def _opportunity_metadata(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "payload_sha256": sha256_json(item),
        "facts": compact_facts(without_keys(item, OPPORTUNITY_COLUMN_KEYS)),
    }


def _upsert_opportunity(
    conn: Any, provider_id: str, item: dict[str, Any], description: str | None = None
) -> str:
    description = description or item.get("description") or item.get("raw_text")
    description_sha = sha256_text(normalize_space(description)) if normalize_space(description) else None
    description_excerpt = excerpt(description)
    aliases = _text_list(item.get("external_id_aliases"))
    evaluation = item.get("evaluation") if isinstance(item.get("evaluation"), dict) else {}
    tags = _text_list(item.get("requirement_tags") or evaluation.get("requirement_tags"))
    company = item.get("company") or item.get("organization") or item.get("client")
    organization_id = _organization(conn, company, {"last_payload_company": company})
    title = (
        normalize_space(item.get("title") or item.get("role_title") or item.get("job_title"))
        or "[UNKNOWN ROLE]"
    )
    external_id = (
        normalize_space(
            item.get("external_id")
            or item.get("provider_external_id")
            or item.get("linkedin_job_id")
            or item.get("upwork_job_id")
        )
        or None
    )
    source_url = normalize_space(item.get("source_url") or item.get("job_url") or item.get("url")) or None
    apply_url = normalize_space(item.get("apply_url") or item.get("application_url")) or source_url
    location = normalize_space(item.get("location") or item.get("location_text")) or None
    opportunity_type = normalize_space(item.get("opportunity_type")) or "employment"

    with conn.cursor() as cur:
        if external_id:
            cur.execute(
                """
                select id from opportunities
                where provider_id = %s and external_id = %s
                """,
                (provider_id, external_id),
            )
            existing = cur.fetchone()
        else:
            cur.execute(
                """
                select id from opportunities
                where provider_id = %s
                  and organization_id is not distinct from %s
                  and normalized_title = %s
                  and location_text is not distinct from %s
                order by created_at asc
                limit 1
                """,
                (provider_id, organization_id, normalize_name(title), location),
            )
            existing = cur.fetchone()

        params = (
            provider_id,
            organization_id,
            opportunity_type,
            title,
            normalize_name(title),
            external_id,
            source_url,
            apply_url,
            location,
            normalize_space(item.get("work_model")) or None,
            normalize_space(
                item.get("engagement_type") or item.get("employment_type") or item.get("job_type")
            )
            or None,
            normalize_space(item.get("seniority")) or None,
            normalize_space(item.get("domain") or item.get("company_domain")) or None,
            normalize_space(item.get("compensation_text") or item.get("salary_listed") or item.get("budget"))
            or None,
            normalize_space(item.get("compensation_currency") or item.get("currency")) or None,
            normalize_space(item.get("budget_type")) or None,
            normalize_space(item.get("source_status")) or "seen",
            parse_timestamp(item.get("first_seen_at") or item.get("first_seen")),
            parse_timestamp(item.get("last_seen_at") or item.get("last_seen")) or utc_now(),
            description_sha,
            description_excerpt,
            aliases,
            tags,
            _json(_opportunity_metadata(item)),
        )
        if existing:
            update_params = (
                provider_id,
                organization_id,
                opportunity_type,
                title,
                normalize_name(title),
                external_id,
                source_url,
                apply_url,
                location,
                normalize_space(item.get("work_model")) or None,
                normalize_space(
                    item.get("engagement_type") or item.get("employment_type") or item.get("job_type")
                )
                or None,
                normalize_space(item.get("seniority")) or None,
                normalize_space(item.get("domain") or item.get("company_domain")) or None,
                normalize_space(
                    item.get("compensation_text") or item.get("salary_listed") or item.get("budget")
                )
                or None,
                normalize_space(item.get("compensation_currency") or item.get("currency")) or None,
                normalize_space(item.get("budget_type")) or None,
                normalize_space(item.get("source_status")) or "seen",
                parse_timestamp(item.get("first_seen_at") or item.get("first_seen")),
                parse_timestamp(item.get("last_seen_at") or item.get("last_seen")) or utc_now(),
                parse_timestamp(item.get("last_seen_at") or item.get("last_seen")) or utc_now(),
                description_sha,
                description_excerpt,
                aliases,
                tags,
                tags,
                _json(_opportunity_metadata(item)),
                existing["id"],
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
                  compensation_text = coalesce(%s, compensation_text),
                  compensation_currency = coalesce(%s, compensation_currency),
                  budget_type = coalesce(%s, budget_type),
                  source_status = coalesce(%s, source_status),
                  first_seen_at = coalesce(first_seen_at, %s),
                  last_seen_at = greatest(coalesce(last_seen_at, %s), %s),
                  description_sha256 = coalesce(%s, description_sha256),
                  description_excerpt = coalesce(%s, description_excerpt),
                  external_id_aliases = (
                    select coalesce(array_agg(distinct alias), '{}')
                    from unnest(external_id_aliases || %s::text[]) as alias
                  ),
                  requirement_tags = case
                    when cardinality(%s::text[]) > 0 then %s::text[]
                    else requirement_tags
                  end,
                  metadata = (metadata - 'payload') || %s::jsonb,
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
                  engagement_type, seniority, domain, compensation_text,
                  compensation_currency, budget_type, source_status,
                  first_seen_at, last_seen_at, description_sha256, description_excerpt,
                  external_id_aliases, requirement_tags, metadata
                )
                values (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s::text[], %s::text[], %s::jsonb
                )
                returning id
                """,
                params,
            )
        return cur.fetchone()["id"]


def _insert_source_item(
    conn: Any,
    provider_id: str,
    run_id: str,
    item: dict[str, Any],
    opportunity_id: str | None = None,
    *,
    keep_raw_text: bool = False,
) -> str:
    raw_text = item.get("raw_text")
    body = normalize_space(raw_text)
    metadata: dict[str, Any] = {"facts": compact_facts(without_keys(item, SOURCE_ITEM_COLUMN_KEYS))}
    if body:
        metadata["raw_text_chars"] = len(raw_text)
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into source_items(
              provider_id, opportunity_id, automation_run_id, source_type,
              external_id, source_url, source_timestamp, title, summary, raw_text,
              body_sha256, metadata
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict(provider_id, source_type, external_id) where external_id is not null
            do update set
              opportunity_id = coalesce(excluded.opportunity_id, source_items.opportunity_id),
              automation_run_id = excluded.automation_run_id,
              source_url = coalesce(excluded.source_url, source_items.source_url),
              source_timestamp = coalesce(excluded.source_timestamp, source_items.source_timestamp),
              title = coalesce(excluded.title, source_items.title),
              summary = coalesce(excluded.summary, source_items.summary),
              raw_text = coalesce(excluded.raw_text, source_items.raw_text),
              body_sha256 = coalesce(excluded.body_sha256, source_items.body_sha256),
              metadata = (source_items.metadata - 'payload') || excluded.metadata,
              updated_at = now()
            returning id
            """,
            (
                provider_id,
                opportunity_id,
                run_id,
                normalize_space(item.get("source_type")) or "automation_source",
                normalize_space(item.get("external_id") or item.get("message_id") or item.get("id")) or None,
                normalize_space(item.get("source_url") or item.get("url") or item.get("gmail_link")) or None,
                parse_timestamp(
                    item.get("timestamp") or item.get("source_timestamp") or item.get("email_date")
                ),
                normalize_space(item.get("title") or item.get("subject")) or None,
                normalize_space(item.get("summary") or item.get("snippet")) or None,
                raw_text if keep_raw_text else None,
                sha256_text(body) if body else None,
                _json(metadata),
            ),
        )
        return cur.fetchone()["id"]


def _link_source_item(conn: Any, provider_id: str, run_id: str, external_id: str, opportunity_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            update source_items
            set opportunity_id = coalesce(opportunity_id, %s),
                automation_run_id = %s,
                updated_at = now()
            where provider_id = %s
              and external_id = %s
            returning id
            """,
            (opportunity_id, run_id, provider_id, external_id),
        )
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute(
            """
            insert into source_items(
              provider_id, opportunity_id, automation_run_id, source_type,
              external_id, summary, metadata
            )
            values (%s, %s, %s, %s, %s, %s, %s::jsonb)
            returning id
            """,
            (
                provider_id,
                opportunity_id,
                run_id,
                "automation_source_ref",
                external_id,
                f"Referenced source item {external_id}",
                _json({"source_reference": external_id}),
            ),
        )
        return cur.fetchone()["id"]


def _insert_evaluation(
    conn: Any, provider_id: str, run_id: str, opportunity_id: str, evaluation: dict[str, Any]
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into evaluations(
              opportunity_id, automation_run_id, provider_id, score, confidence,
              recommendation, priority, verdict, main_match, main_risks,
              missing_information, positioning_angle, salary_expectation,
              pricing_recommendation, proposal_text, action_next,
              manual_review_reason, metadata
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            returning id
            """,
            (
                opportunity_id,
                run_id,
                provider_id,
                evaluation.get("score"),
                evaluation.get("confidence"),
                evaluation.get("recommendation"),
                evaluation.get("priority"),
                evaluation.get("verdict"),
                evaluation.get("main_match") or evaluation.get("reason"),
                evaluation.get("main_risks") or evaluation.get("risk"),
                evaluation.get("missing_information"),
                evaluation.get("positioning_angle"),
                evaluation.get("salary_expectation"),
                evaluation.get("pricing_recommendation"),
                evaluation.get("proposal_text"),
                evaluation.get("action_next") or evaluation.get("action"),
                evaluation.get("manual_review_reason"),
                _json({"facts": compact_facts(without_keys(evaluation, EVALUATION_COLUMN_KEYS))}),
            ),
        )
        return cur.fetchone()["id"]


def _insert_application(conn: Any, provider_id: str, opportunity_id: str, application: dict[str, Any]) -> str:
    """Create the opportunity's application, or update it on replay (never duplicates)."""
    metadata = _json({"facts": compact_facts(without_keys(application, APPLICATION_COLUMN_KEYS))})
    with conn.cursor() as cur:
        cur.execute("select organization_id from opportunities where id = %s", (opportunity_id,))
        row = cur.fetchone()
        organization_id = row["organization_id"] if row else None
        cur.execute(
            "select id from applications where opportunity_id = %s order by created_at asc limit 1",
            (opportunity_id,),
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                """
                update applications set
                  application_channel = coalesce(%s, application_channel),
                  status = coalesce(%s, status),
                  current_stage = coalesce(%s, current_stage),
                  applied_at = coalesce(%s, applied_at),
                  salary_requested_text = coalesce(%s, salary_requested_text),
                  outcome = coalesce(%s, outcome),
                  decline_reason = coalesce(%s, decline_reason),
                  notes = coalesce(%s, notes),
                  metadata = (metadata - 'payload') || %s::jsonb,
                  updated_at = now()
                where id = %s
                returning id
                """,
                (
                    application.get("application_channel"),
                    application.get("status"),
                    application.get("current_stage") or application.get("stage"),
                    application.get("applied_at"),
                    application.get("salary_requested_text"),
                    application.get("outcome"),
                    application.get("decline_reason"),
                    application.get("notes"),
                    metadata,
                    existing["id"],
                ),
            )
            return cur.fetchone()["id"]
        cur.execute(
            """
            insert into applications(
              opportunity_id, organization_id, provider_id, application_channel,
              status, current_stage, applied_at, salary_requested_text,
              outcome, decline_reason, notes, metadata
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            returning id
            """,
            (
                opportunity_id,
                organization_id,
                provider_id,
                application.get("application_channel"),
                application.get("status") or "applied",
                application.get("current_stage") or application.get("stage"),
                application.get("applied_at"),
                application.get("salary_requested_text"),
                application.get("outcome"),
                application.get("decline_reason"),
                application.get("notes"),
                metadata,
            ),
        )
        return cur.fetchone()["id"]


def _run_metadata(payload: dict[str, Any], payload_path: str | Path, payload_sha: str) -> dict[str, Any]:
    """Compact run facts. ``payload_sha256`` hashes the payload file as read from disk."""
    run = payload.get("run") or {}
    metadata: dict[str, Any] = {
        "payload_sha256": payload_sha,
        "payload_path": str(payload_path),
        "source_items": len(payload.get("source_items") or []),
        "opportunities": len(payload.get("opportunities") or []),
    }
    if payload.get("manual_review_blockers"):
        metadata["manual_review_blockers"] = compact_facts(payload["manual_review_blockers"])
    if isinstance(run, dict) and run.get("metrics"):
        metadata["metrics"] = compact_facts(run["metrics"])
    if isinstance(payload.get("metadata"), dict):
        metadata["facts"] = compact_facts(payload["metadata"])
    return metadata


def _source_texts(payload: dict[str, Any]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for source in payload.get("source_items") or payload.get("emails") or []:
        if not isinstance(source, dict):
            continue
        external_id = normalize_space(
            source.get("external_id") or source.get("message_id") or source.get("id")
        )
        raw_text = source.get("raw_text")
        if external_id and isinstance(raw_text, str) and normalize_space(raw_text):
            texts[external_id] = raw_text
    return texts


def _opportunity_text(item: dict[str, Any], texts: dict[str, str]) -> tuple[str | None, str | None]:
    for key in ("description", "raw_text"):
        value = item.get(key)
        if isinstance(value, str) and normalize_space(value):
            return value, None
    for source in item.get("source_items") or []:
        if isinstance(source, dict):
            value = source.get("raw_text")
            ref = normalize_space(source.get("external_id"))
            if isinstance(value, str) and normalize_space(value):
                return value, ref or None
        else:
            ref = normalize_space(str(source))
            if ref in texts:
                return texts[ref], ref
    return None, None


def _store_opportunity_text(
    conn: Any, opportunity_id: str, text: str, reason: str, source_ref: str | None
) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into opportunity_texts(
              opportunity_id, content_sha256, body, retention_reason, source_item_external_id, fetched_at
            )
            values (%s, %s, %s, %s, %s, now())
            on conflict(opportunity_id, content_sha256) do nothing
            returning id
            """,
            (opportunity_id, sha256_text(normalize_space(text)), text, reason, source_ref),
        )
        return cur.fetchone() is not None


def _store_report_document(conn: Any, report_path: str, run_id: str, run_key: str) -> str | None:
    path = Path(report_path)
    if not path.exists():
        return None
    body = path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into documents(
              kind, status, title, body, content_sha256, source_key, automation_run_id, created_by, metadata
            )
            values ('report', 'final', %s, %s, %s, %s, %s, 'automation', %s::jsonb)
            on conflict(source_key) where source_key is not null do update set
              body = excluded.body,
              content_sha256 = excluded.content_sha256,
              automation_run_id = excluded.automation_run_id,
              updated_at = now()
            returning id
            """,
            (
                path.name,
                body,
                sha256_text(body),
                f"report:{run_key}:{path.name}",
                run_id,
                _json({"local_path": str(path)}),
            ),
        )
        return cur.fetchone()["id"]


def _upsert_run_payload(
    conn: Any,
    provider_slug: str,
    payload_path: str | Path,
    report_path: str | None = None,
    *,
    text_retention: str = "shortlisted",
    artifact_backend: str = "local",
) -> UpsertResult:
    text_retention = normalize_text_retention(text_retention)
    payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    payload_sha = sha256_json(payload)
    provider_slug = slugify(provider_slug)
    validation = validate_payload(payload, provider=provider_slug)
    if validation.errors:
        raise ValueError(f"Invalid automation payload: {'; '.join(validation.errors)}")
    payload = validation.normalized
    run = payload.get("run") or {}
    run_key = normalize_space(run.get("run_key") or payload.get("run_key"))
    if not run_key:
        timestamp = normalize_space(run.get("started_at") or run.get("finished_at")) or utc_now().isoformat()
        run_key = f"{provider_slug}-{slugify(timestamp)}"

    with conn.transaction():
        provider_id = _provider(conn, provider_slug)
        report_artifact_id = (
            _artifact(conn, report_path, provider_slug, run_key, artifact_backend) if report_path else None
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into automation_runs(
                  provider_id, run_key, started_at, finished_at, status, report_artifact_id,
                  report_email_sent, report_email_subject, source_items_count,
                  opportunities_count, evaluations_count, manual_review_count, summary, metadata
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                on conflict(run_key) do update set
                  finished_at = excluded.finished_at,
                  status = excluded.status,
                  report_artifact_id = coalesce(excluded.report_artifact_id, automation_runs.report_artifact_id),
                  report_email_sent = excluded.report_email_sent,
                  report_email_subject = excluded.report_email_subject,
                  source_items_count = excluded.source_items_count,
                  opportunities_count = excluded.opportunities_count,
                  evaluations_count = excluded.evaluations_count,
                  manual_review_count = excluded.manual_review_count,
                  summary = excluded.summary,
                  metadata = (automation_runs.metadata - 'payload') || excluded.metadata,
                  updated_at = now()
                returning id
                """,
                (
                    provider_id,
                    run_key,
                    parse_timestamp(run.get("started_at")),
                    parse_timestamp(run.get("finished_at")),
                    run.get("status") or "completed",
                    report_artifact_id,
                    run.get("report_email_sent") or run.get("email_sent"),
                    run.get("report_email_subject") or run.get("email_subject"),
                    int(run.get("source_items_count") or len(payload.get("source_items") or [])),
                    int(run.get("opportunities_count") or len(payload.get("opportunities") or [])),
                    int(run.get("evaluations_count") or 0),
                    int(run.get("manual_review_count") or len(payload.get("manual_review_blockers") or [])),
                    run.get("summary") or payload.get("summary"),
                    _json(_run_metadata(payload, payload_path, payload_sha)),
                ),
            )
            run_id = cur.fetchone()["id"]
            cur.execute("delete from evaluations where automation_run_id = %s", (run_id,))

        keep_raw = text_retention == "all"
        texts = _source_texts(payload)
        for source in payload.get("source_items") or payload.get("emails") or []:
            _insert_source_item(conn, provider_id, run_id, source, keep_raw_text=keep_raw)

        opportunity_count = 0
        evaluation_count = 0
        stored_texts = 0
        for item in payload.get("opportunities") or payload.get("jobs") or []:
            text, text_ref = _opportunity_text(item, texts)
            opportunity_id = _upsert_opportunity(conn, provider_id, item, description=text)
            opportunity_count += 1
            reason = keep_full_text(item, text_retention)
            if text and reason and _store_opportunity_text(conn, opportunity_id, text, reason, text_ref):
                stored_texts += 1
            for source in item.get("source_items") or []:
                if isinstance(source, dict):
                    _insert_source_item(
                        conn, provider_id, run_id, source, opportunity_id, keep_raw_text=keep_raw
                    )
                else:
                    source_ref = normalize_space(str(source))
                    if source_ref:
                        _link_source_item(conn, provider_id, run_id, source_ref, opportunity_id)
            evaluation = item.get("evaluation")
            if evaluation:
                _insert_evaluation(conn, provider_id, run_id, opportunity_id, evaluation)
                evaluation_count += 1
            application = item.get("application")
            if application:
                _insert_application(conn, provider_id, opportunity_id, application)

        with conn.cursor() as cur:
            cur.execute(
                """
                update automation_runs
                set opportunities_count = %s,
                    evaluations_count = %s,
                    updated_at = now()
                where id = %s
                """,
                (opportunity_count, evaluation_count, run_id),
            )
        report_document_id = (
            _store_report_document(conn, report_path, run_id, run_key) if report_path else None
        )

    return UpsertResult(
        run_key=run_key,
        opportunities=opportunity_count,
        evaluations=evaluation_count,
        stored_texts=stored_texts,
        report_document_id=str(report_document_id) if report_document_id else None,
    )


def _verify_run(conn: Any, run_key: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            select r.run_key, r.status, r.opportunities_count, r.evaluations_count,
                   r.metadata ->> 'payload_sha256' as payload_sha256, r.updated_at
            from automation_runs r
            where r.run_key = %s
            """,
            (run_key,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _record_payload_sha256(conn: Any, run_key: str, payload_sha256: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            update automation_runs
            set metadata = metadata || jsonb_build_object('payload_sha256', %s::text)
            where run_key = %s and coalesce(metadata ->> 'payload_sha256', '') = ''
            """,
            (payload_sha256, run_key),
        )
        return cur.rowcount > 0


def _check_duplicates(
    conn: Any, provider_slug: str, company: str | None, title: str | None, external_id: str | None = None
) -> list[dict[str, Any]]:
    provider_slug = slugify(provider_slug)
    normalized_company = normalize_name(company)
    normalized_title = normalize_name(title)
    normalized_external_id = (
        validate_payload(
            {
                "run": {"run_key": f"{provider_slug}-duplicate-check"},
                "opportunities": [
                    {
                        "title": title or "[unknown]",
                        "external_id": external_id or "",
                        "source_url": external_id or "",
                    }
                ],
            },
            provider=provider_slug,
        )
        .normalized["opportunities"][0]
        .get("external_id")
        if external_id
        else None
    )
    rows: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        if normalized_external_id:
            cur.execute(
                """
                select
                  'exact_external_id' as match_type,
                  o.id as opportunity_id,
                  o.title,
                  o.source_url,
                  o.apply_url,
                  o.location_text,
                  o.work_model,
                  org.name as company,
                  a.id as application_id,
                  a.status as application_status,
                  a.applied_at,
                  coalesce(run_evidence.automation_run_keys, '{}'::text[]) as automation_run_keys
                from opportunities o
                join providers p on p.id = o.provider_id
                left join organizations org on org.id = o.organization_id
                left join applications a on a.opportunity_id = o.id
                left join lateral (
                  select array_remove(array_agg(distinct ar.run_key), null) as automation_run_keys
                  from (
                    select e.automation_run_id
                    from evaluations e
                    where e.opportunity_id = o.id
                    union
                    select si.automation_run_id
                    from source_items si
                    where si.opportunity_id = o.id
                  ) rel
                  join automation_runs ar on ar.id = rel.automation_run_id
                ) run_evidence on true
                where p.slug = %s and o.external_id = %s
                order by coalesce(a.applied_at, o.created_at::date) desc nulls last
                limit 20
                """,
                (provider_slug, normalized_external_id),
            )
            rows.extend(dict(row) for row in cur.fetchall())

        if normalized_company and normalized_title:
            cur.execute(
                """
                select
                  'exact_company_title' as match_type,
                  o.id as opportunity_id,
                  o.title,
                  o.source_url,
                  o.apply_url,
                  o.location_text,
                  o.work_model,
                  org.name as company,
                  a.id as application_id,
                  a.status as application_status,
                  a.applied_at,
                  coalesce(run_evidence.automation_run_keys, '{}'::text[]) as automation_run_keys
                from opportunities o
                join providers p on p.id = o.provider_id
                left join organizations org on org.id = o.organization_id
                left join applications a on a.opportunity_id = o.id
                left join lateral (
                  select array_remove(array_agg(distinct ar.run_key), null) as automation_run_keys
                  from (
                    select e.automation_run_id
                    from evaluations e
                    where e.opportunity_id = o.id
                    union
                    select si.automation_run_id
                    from source_items si
                    where si.opportunity_id = o.id
                  ) rel
                  join automation_runs ar on ar.id = rel.automation_run_id
                ) run_evidence on true
                where p.slug = %s
                  and org.normalized_name = %s
                  and o.normalized_title = %s
                order by coalesce(a.applied_at, o.created_at::date) desc nulls last
                limit 20
                """,
                (provider_slug, normalized_company, normalized_title),
            )
            rows.extend(dict(row) for row in cur.fetchall())

        if normalized_company:
            cur.execute(
                """
                select
                  'same_company_recent_application' as match_type,
                  o.id as opportunity_id,
                  o.title,
                  o.source_url,
                  o.apply_url,
                  o.location_text,
                  o.work_model,
                  org.name as company,
                  a.id as application_id,
                  a.status as application_status,
                  a.applied_at,
                  coalesce(run_evidence.automation_run_keys, '{}'::text[]) as automation_run_keys
                from applications a
                join opportunities o on o.id = a.opportunity_id
                left join organizations org on org.id = coalesce(a.organization_id, o.organization_id)
                left join providers p on p.id = coalesce(a.provider_id, o.provider_id)
                left join lateral (
                  select array_remove(array_agg(distinct ar.run_key), null) as automation_run_keys
                  from (
                    select e.automation_run_id
                    from evaluations e
                    where e.opportunity_id = o.id
                    union
                    select si.automation_run_id
                    from source_items si
                    where si.opportunity_id = o.id
                  ) rel
                  join automation_runs ar on ar.id = rel.automation_run_id
                ) run_evidence on true
                where org.normalized_name = %s
                  and a.applied_at >= current_date - interval '180 days'
                order by a.applied_at desc nulls last, a.created_at desc
                limit 20
                """,
                (normalized_company,),
            )
            rows.extend(dict(row) for row in cur.fetchall())

    seen: set[tuple[Any, Any, Any]] = set()
    unique_rows: list[dict[str, Any]] = []
    for row in rows:
        key = (row.get("match_type"), row.get("opportunity_id"), row.get("application_id"))
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows[:20]


def _export_application_summary(conn: Any, application_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            select
              a.*, o.title as opportunity_title, o.source_url, o.apply_url,
              org.name as company, p.name as provider
            from applications a
            left join opportunities o on o.id = a.opportunity_id
            left join organizations org on org.id = a.organization_id
            left join providers p on p.id = a.provider_id
            where a.id = %s
            """,
            (application_id,),
        )
        app = cur.fetchone()
        if not app:
            raise ValueError(f"Application not found: {application_id}")
        cur.execute(
            """
            select event_type, event_at, title, description
            from application_events
            where application_id = %s
            order by event_at nulls last, created_at
            """,
            (application_id,),
        )
        events = cur.fetchall()

    lines = [
        f"# Application summary: {app.get('company') or '[Unknown company]'}",
        "",
        f"- Opportunity: {app.get('opportunity_title') or '[Unknown role]'}",
        f"- Provider: {app.get('provider') or '[Unknown]'}",
        f"- Status: {app.get('status') or '[Unknown]'}",
        f"- Current stage: {app.get('current_stage') or '[Unknown]'}",
        f"- Applied at: {app.get('applied_at') or '[Unknown]'}",
        f"- Salary requested: {app.get('salary_requested_text') or '[Unknown]'}",
        f"- Source: {app.get('source_url') or '[Unknown]'}",
        f"- Apply: {app.get('apply_url') or '[Unknown]'}",
        "",
        "## Notes",
        app.get("notes") or "[None]",
        "",
        "## Timeline",
    ]
    if not events:
        lines.append("- [No events recorded]")
    for event in events:
        lines.append(
            f"- {event.get('event_at') or '[No date]'}: {event.get('event_type')} - {event.get('title') or event.get('description') or ''}"
        )
    return "\n".join(lines)


class PostgresJobStore:
    backend = "postgres"

    def __init__(self, conn: Any, options: dict[str, Any] | None = None) -> None:
        self.conn = conn
        self.options = dict(options or {})
        self.text_retention = normalize_text_retention(self.options.get("text_retention"))

    def upsert_run_payload(
        self,
        provider_slug: str,
        payload_path: str | Path,
        report_path: str | None = None,
    ) -> UpsertResult:
        return _upsert_run_payload(
            self.conn,
            provider_slug,
            payload_path,
            report_path=report_path,
            text_retention=self.text_retention,
            artifact_backend=str(self.options.get("artifact_backend") or "local"),
        )

    def verify_run(self, run_key: str) -> dict[str, Any] | None:
        """Read back a stored run; ``None`` means the run is not in the database."""
        return _verify_run(self.conn, run_key)

    def record_payload_sha256(self, run_key: str, payload_sha256: str) -> bool:
        """Store the payload hash on a run that has none, without rewriting the run."""
        return _record_payload_sha256(self.conn, run_key, payload_sha256)

    def commit(self) -> None:
        """Commit the connection's open transaction (the connection is not autocommit)."""
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def find_document_by_sha(self, content_sha256: str) -> dict[str, Any] | None:
        from .postgres_documents import find_document_by_sha

        return find_document_by_sha(self.conn, content_sha256)

    def check_duplicates(
        self,
        provider_slug: str,
        company: str | None,
        title: str | None,
        external_id: str | None = None,
    ) -> list[DuplicateMatch]:
        rows = _check_duplicates(self.conn, provider_slug, company, title, external_id=external_id)
        return [
            DuplicateMatch(
                match_type=row.get("match_type") or "",
                opportunity_id=row.get("opportunity_id"),
                title=row.get("title"),
                source_url=row.get("source_url"),
                apply_url=row.get("apply_url"),
                location_text=row.get("location_text"),
                work_model=row.get("work_model"),
                company=row.get("company"),
                application_id=row.get("application_id"),
                application_status=row.get("application_status"),
                applied_at=str(row.get("applied_at")) if row.get("applied_at") is not None else None,
                automation_run_keys=list(row.get("automation_run_keys") or []),
            )
            for row in rows
        ]

    def export_application_summary(self, application_id: str) -> str:
        return _export_application_summary(self.conn, application_id)
