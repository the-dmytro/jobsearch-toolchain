from __future__ import annotations

from pathlib import Path
from typing import Any

from .store.generic.postgres import PostgresJobStore


def upsert_run_payload(
    conn: Any, provider_slug: str, payload_path: str | Path, report_path: str | None = None
) -> dict[str, Any]:
    result = PostgresJobStore(conn).upsert_run_payload(provider_slug, payload_path, report_path=report_path)
    return {
        "run_key": result.run_key,
        "opportunities": result.opportunities,
        "evaluations": result.evaluations,
    }


def check_duplicates(
    conn: Any,
    provider_slug: str,
    company: str | None,
    title: str | None,
    external_id: str | None = None,
) -> list[dict[str, Any]]:
    matches = PostgresJobStore(conn).check_duplicates(provider_slug, company, title, external_id=external_id)
    return [match.as_dict() for match in matches]


def export_application_summary(conn: Any, application_id: str) -> str:
    return PostgresJobStore(conn).export_application_summary(application_id)
