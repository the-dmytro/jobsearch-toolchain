from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .pdf_links import PdfLink, extract_pdf_links
from .url_tools import clean_url
from .utils import (
    json_default,
    normalize_name,
    normalize_space,
    parse_legacy_date,
    parse_money_range,
    sha256_text,
    slugify,
)

EXPECTED_FIELDS = [
    "Company",
    "Location",
    "Kind",
    "Domain",
    "Vacancy link",
    "Source",
    "Application date",
    "Salary requested",
    "Stage",
    "Decline reason",
    "Passed",
    "Notes",
]


@dataclass
class LegacyRecord:
    row_number: int
    raw_row: dict[str, str]
    source_file: str
    stable_key: str
    fallback_key: str
    company: str
    provider_slug: str
    provider_name: str
    opportunity_title: str
    source_url: str | None
    link_urls: list[str]
    link_sources: list[dict[str, Any]]
    applied_at: Any
    salary: dict[str, Any]
    warnings: list[str]


def provider_from_source(source: str | None) -> tuple[str, str]:
    text = normalize_space(source)
    if not text:
        return "manual_import", "Manual import"
    aliases = {
        "linkedin": ("linkedin", "LinkedIn"),
        "djinny": ("djinni", "Djinni"),
        "djinni": ("djinni", "Djinni"),
    }
    return aliases.get(text.lower(), (slugify(text, "manual_import"), text))


def read_legacy_csv(path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    csv_path = Path(path)
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        rows = [dict(row) for row in reader]
        fields = list(reader.fieldnames or [])
    return fields, rows


def _link_label_count(value: str | None) -> int:
    text = normalize_space(value)
    if not text:
        return 0
    return len([part for part in re.split(r"\s*,\s*", text) if normalize_space(part)])


def _is_placeholder_link_text(value: str | None) -> bool:
    text = normalize_space(value).lower()
    if not text:
        return False
    parts = [normalize_space(part).lower() for part in re.split(r"\s*,\s*", text) if normalize_space(part)]
    return bool(parts) and all(part in {"link", "links", "link 1", "link 2"} for part in parts)


def _auto_pdf_path(csv_path: Path) -> Path | None:
    candidate = csv_path.with_suffix(".pdf")
    return candidate if candidate.exists() else None


def _pdf_overrides(
    path: str | Path, links_pdf: str | Path | None
) -> tuple[list[PdfLink], list[dict[str, Any]]]:
    csv_path = Path(path)
    pdf_path = Path(links_pdf) if links_pdf else _auto_pdf_path(csv_path)
    if not pdf_path:
        return [], []
    try:
        return extract_pdf_links(pdf_path), []
    except RuntimeError as exc:
        raise ValueError(f"Could not extract links from {pdf_path}: {exc}") from exc


def build_legacy_records(
    path: str | Path, links_pdf: str | Path | None = None
) -> tuple[list[LegacyRecord], list[dict[str, Any]]]:
    csv_path = Path(path)
    fields, rows = read_legacy_csv(csv_path)
    pdf_links, pdf_warnings = _pdf_overrides(csv_path, links_pdf)
    pdf_index = 0
    skipped: list[dict[str, Any]] = []
    skipped.extend(pdf_warnings)
    records: list[LegacyRecord] = []
    if fields != EXPECTED_FIELDS:
        skipped.append({"row_number": 0, "reason": "unexpected_header", "fields": fields})

    for row_number, row in enumerate(rows, start=2):
        company = normalize_space(row.get("Company"))
        if not company:
            skipped.append({"row_number": row_number, "reason": "empty_company", "row": row})
            continue

        original_link_text = normalize_space(row.get("Vacancy link"))
        link_urls: list[str] = []
        link_sources: list[dict[str, Any]] = []
        if _is_placeholder_link_text(original_link_text):
            for _ in range(_link_label_count(original_link_text)):
                if pdf_index >= len(pdf_links):
                    break
                link = pdf_links[pdf_index]
                pdf_index += 1
                link_urls.append(link.url)
                link_sources.append(
                    {
                        "source": "pdf_annotation",
                        "raw_url": link.raw_url,
                        "page_number": link.page_number,
                        "annotation_index": link.annotation_index,
                        "rect": list(link.rect),
                    }
                )
        else:
            for part in [part for part in re.split(r"\s*,\s*", original_link_text) if normalize_space(part)]:
                cleaned = clean_url(part)
                if cleaned:
                    link_urls.append(cleaned)
                    link_sources.append({"source": "csv", "raw_url": normalize_space(part)})

        source = normalize_space(row.get("Source"))
        provider_slug, provider_name = provider_from_source(source)
        applied_at = parse_legacy_date(row.get("Application date"))
        source_url = link_urls[0] if link_urls else None
        warnings: list[str] = []
        if original_link_text and not source_url:
            warnings.append("legacy_link_placeholder_or_non_url")
        if _is_placeholder_link_text(original_link_text) and not link_urls:
            warnings.append("pdf_link_missing_for_placeholder")
        if row.get("Application date") and not applied_at:
            warnings.append("application_date_unparsed")

        fallback_parts = [
            normalize_name(company),
            normalize_name(row.get("Application date")),
            normalize_name(row.get("Source")),
            normalize_name(row.get("Stage")),
            normalize_name(row.get("Domain")),
        ]
        fallback_key = sha256_text("|".join(fallback_parts))
        stable_key = sha256_text(f"{csv_path.name}|{row_number}|{fallback_key}")
        salary = parse_money_range(row.get("Salary requested"))
        records.append(
            LegacyRecord(
                row_number=row_number,
                raw_row=row,
                source_file=str(csv_path),
                stable_key=stable_key,
                fallback_key=fallback_key,
                company=company,
                provider_slug=provider_slug,
                provider_name=provider_name,
                opportunity_title="[UNKNOWN ROLE]",
                source_url=source_url,
                link_urls=link_urls,
                link_sources=link_sources,
                applied_at=applied_at,
                salary=salary,
                warnings=warnings,
            )
        )
    return records, skipped


def summarize_legacy_csv(path: str | Path, links_pdf: str | Path | None = None) -> dict[str, Any]:
    records, skipped = build_legacy_records(path, links_pdf=links_pdf)
    by_provider: dict[str, int] = {}
    by_stage: dict[str, int] = {}
    warnings: dict[str, int] = {}
    pdf_link_rows = 0
    linked_rows = 0
    for record in records:
        by_provider[record.provider_slug] = by_provider.get(record.provider_slug, 0) + 1
        stage = normalize_space(record.raw_row.get("Stage")) or "[blank]"
        by_stage[stage] = by_stage.get(stage, 0) + 1
        if record.link_urls:
            linked_rows += 1
        if any(source["source"] == "pdf_annotation" for source in record.link_sources):
            pdf_link_rows += 1
        for warning in record.warnings:
            warnings[warning] = warnings.get(warning, 0) + 1
    return {
        "source": str(path),
        "usable_rows": len(records),
        "skipped_rows": len(skipped),
        "skipped": skipped,
        "providers": by_provider,
        "stages": by_stage,
        "warnings": warnings,
        "linked_rows": linked_rows,
        "pdf_link_rows": pdf_link_rows,
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=json_default)


def import_legacy_csv(conn: Any, path: str | Path, links_pdf: str | Path | None = None) -> dict[str, Any]:
    records, skipped = build_legacy_records(path, links_pdf=links_pdf)
    stats = {"records": len(records), "skipped": len(skipped), "created_or_updated": 0, "warnings": skipped}

    with conn.transaction():
        for record in records:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into providers(slug, name, provider_type)
                    values (%s, %s, %s)
                    on conflict(slug) do update set name = excluded.name, updated_at = now()
                    returning id
                    """,
                    (
                        record.provider_slug,
                        record.provider_name,
                        "job_board" if record.provider_slug != "manual_import" else "manual",
                    ),
                )
                provider_id = cur.fetchone()["id"]

                cur.execute(
                    """
                    insert into organizations(name, normalized_name, industry, location_text, metadata)
                    values (%s, %s, %s, %s, %s::jsonb)
                    on conflict(normalized_name) do update set
                      industry = coalesce(organizations.industry, excluded.industry),
                      location_text = coalesce(organizations.location_text, excluded.location_text),
                      metadata = organizations.metadata || excluded.metadata,
                      updated_at = now()
                    returning id
                    """,
                    (
                        record.company,
                        normalize_name(record.company),
                        normalize_space(record.raw_row.get("Domain")) or None,
                        normalize_space(record.raw_row.get("Location")) or None,
                        _json({"legacy_sources": [record.source_file]}),
                    ),
                )
                organization_id = cur.fetchone()["id"]

                cur.execute(
                    """
                    select opportunity_id, application_id, source_item_id
                    from legacy_import_rows
                    where source_file = %s and row_number = %s
                    """,
                    (record.source_file, record.row_number),
                )
                existing = cur.fetchone()
                if not existing:
                    cur.execute(
                        """
                        select opportunity_id, application_id, source_item_id
                        from legacy_import_rows
                        where source_file = %s and fallback_key = %s
                        """,
                        (record.source_file, record.fallback_key),
                    )
                    existing = cur.fetchone()

                opportunity_metadata = {
                    "legacy_import": True,
                    "legacy_row_number": record.row_number,
                    "legacy_raw_row": record.raw_row,
                    "original_link_text": normalize_space(record.raw_row.get("Vacancy link")) or None,
                    "link_urls": record.link_urls,
                    "link_sources": record.link_sources,
                }
                opportunity_params = (
                    provider_id,
                    organization_id,
                    "employment",
                    record.opportunity_title,
                    normalize_name(record.opportunity_title),
                    record.source_url,
                    record.source_url,
                    normalize_space(record.raw_row.get("Location")) or None,
                    normalize_space(record.raw_row.get("Kind")) or None,
                    normalize_space(record.raw_row.get("Domain")) or None,
                    record.salary["text"],
                    record.salary["min"],
                    record.salary["max"],
                    record.salary["currency"],
                    "historical_application",
                    _json(opportunity_metadata),
                )
                if existing and existing.get("opportunity_id"):
                    cur.execute(
                        """
                        update opportunities set
                          provider_id = %s,
                          organization_id = %s,
                          opportunity_type = %s,
                          title = %s,
                          normalized_title = %s,
                          source_url = coalesce(%s, source_url),
                          apply_url = coalesce(%s, apply_url),
                          location_text = %s,
                          work_model = %s,
                          domain = %s,
                          compensation_text = %s,
                          compensation_min = %s,
                          compensation_max = %s,
                          compensation_currency = %s,
                          source_status = %s,
                          metadata = metadata || %s::jsonb,
                          updated_at = now()
                        where id = %s
                        returning id
                        """,
                        (*opportunity_params, existing["opportunity_id"]),
                    )
                else:
                    cur.execute(
                        """
                        insert into opportunities(
                          provider_id, organization_id, opportunity_type, title, normalized_title,
                          source_url, apply_url, location_text, work_model, domain,
                          compensation_text, compensation_min, compensation_max, compensation_currency,
                          source_status, metadata
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        returning id
                        """,
                        opportunity_params,
                    )
                opportunity_id = cur.fetchone()["id"]

                application_metadata = {
                    "legacy_import": True,
                    "legacy_row_number": record.row_number,
                    "legacy_passed_value": normalize_space(record.raw_row.get("Passed")) or None,
                }
                application_params = (
                    opportunity_id,
                    organization_id,
                    provider_id,
                    record.provider_slug,
                    normalize_space(record.raw_row.get("Stage")) or "applied",
                    normalize_space(record.raw_row.get("Stage")) or None,
                    record.applied_at,
                    record.salary["text"],
                    record.salary["min"],
                    record.salary["max"],
                    record.salary["currency"],
                    normalize_space(record.raw_row.get("Stage")) or None,
                    normalize_space(record.raw_row.get("Decline reason")) or None,
                    True if normalize_space(record.raw_row.get("Passed")) else None,
                    normalize_space(record.raw_row.get("Notes")) or None,
                    _json(application_metadata),
                )
                if existing and existing.get("application_id"):
                    cur.execute(
                        """
                        update applications set
                          opportunity_id = %s,
                          organization_id = %s,
                          provider_id = %s,
                          application_channel = %s,
                          status = %s,
                          current_stage = %s,
                          applied_at = %s,
                          salary_requested_text = %s,
                          salary_requested_min = %s,
                          salary_requested_max = %s,
                          salary_requested_currency = %s,
                          outcome = %s,
                          decline_reason = %s,
                          passed = %s,
                          notes = %s,
                          metadata = metadata || %s::jsonb,
                          updated_at = now()
                        where id = %s
                        returning id
                        """,
                        (*application_params, existing["application_id"]),
                    )
                else:
                    cur.execute(
                        """
                        insert into applications(
                          opportunity_id, organization_id, provider_id, application_channel,
                          status, current_stage, applied_at, salary_requested_text,
                          salary_requested_min, salary_requested_max, salary_requested_currency,
                          outcome, decline_reason, passed, notes, metadata
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        returning id
                        """,
                        application_params,
                    )
                application_id = cur.fetchone()["id"]

                source_metadata = {
                    "legacy_import": True,
                    "raw_row": record.raw_row,
                    "original_link_text": normalize_space(record.raw_row.get("Vacancy link")) or None,
                    "link_urls": record.link_urls,
                    "link_sources": record.link_sources,
                }
                if existing and existing.get("source_item_id"):
                    cur.execute(
                        """
                        update source_items set
                          provider_id = %s,
                          opportunity_id = %s,
                          source_type = 'legacy_csv_row',
                          source_url = coalesce(%s, source_url),
                          title = %s,
                          summary = %s,
                          metadata = metadata || %s::jsonb,
                          updated_at = now()
                        where id = %s
                        returning id
                        """,
                        (
                            provider_id,
                            opportunity_id,
                            record.source_url,
                            record.company,
                            f"Legacy application row for {record.company}",
                            _json(source_metadata),
                            existing["source_item_id"],
                        ),
                    )
                else:
                    cur.execute(
                        """
                        insert into source_items(provider_id, opportunity_id, source_type, source_url, title, summary, metadata)
                        values (%s, %s, 'legacy_csv_row', %s, %s, %s, %s::jsonb)
                        returning id
                        """,
                        (
                            provider_id,
                            opportunity_id,
                            record.source_url,
                            record.company,
                            f"Legacy application row for {record.company}",
                            _json(source_metadata),
                        ),
                    )
                source_item_id = cur.fetchone()["id"]

                cur.execute(
                    """
                    insert into legacy_import_rows(
                      source_file, row_number, stable_key, fallback_key, raw_row, original_link_text,
                      provider_id, organization_id, opportunity_id, application_id, source_item_id, import_warnings
                    )
                    values (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
                    on conflict(source_file, row_number) do update set
                      stable_key = excluded.stable_key,
                      fallback_key = excluded.fallback_key,
                      raw_row = excluded.raw_row,
                      original_link_text = excluded.original_link_text,
                      provider_id = excluded.provider_id,
                      organization_id = excluded.organization_id,
                      opportunity_id = excluded.opportunity_id,
                      application_id = excluded.application_id,
                      source_item_id = excluded.source_item_id,
                      import_warnings = excluded.import_warnings,
                      updated_at = now()
                    """,
                    (
                        record.source_file,
                        record.row_number,
                        record.stable_key,
                        record.fallback_key,
                        _json(record.raw_row),
                        normalize_space(record.raw_row.get("Vacancy link")) or None,
                        provider_id,
                        organization_id,
                        opportunity_id,
                        application_id,
                        source_item_id,
                        record.warnings,
                    ),
                )
                stats["created_or_updated"] += 1
    return stats
