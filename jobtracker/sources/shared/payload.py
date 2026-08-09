from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jobtracker.core.models import Candidate, ExistingRef, FetchMetrics
from jobtracker.db import fetch_all
from jobtracker.utils import json_default, parse_timestamp

DEFAULT_OUTPUT_DIR = Path("outputs/provider-fetch")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=json_default, indent=2)


def _load_existing_refs(
    conn: Any | None, provider_slug: str, candidates: list[Candidate]
) -> tuple[dict[str, ExistingRef], dict[str, ExistingRef]]:
    if not conn or not candidates:
        return {}, {}

    external_ids = sorted({candidate.external_id for candidate in candidates if candidate.external_id})
    source_urls = sorted({candidate.source_url for candidate in candidates if candidate.source_url})
    clauses: list[str] = []
    params: list[Any] = [provider_slug]
    if external_ids:
        clauses.append("o.external_id = any(%s)")
        params.append(external_ids)
    if source_urls:
        clauses.append("o.source_url = any(%s)")
        params.append(source_urls)
    if not clauses:
        return {}, {}

    rows = fetch_all(
        conn,
        f"""
        select o.external_id, o.source_url, o.last_seen_at
        from opportunities o
        join providers p on p.id = o.provider_id
        where p.slug = %s
          and ({" or ".join(clauses)})
        """,
        tuple(params),
    )
    by_external_id: dict[str, ExistingRef] = {}
    by_source_url: dict[str, ExistingRef] = {}
    for row in rows:
        ref = ExistingRef(row.get("external_id"), row.get("source_url"), row.get("last_seen_at"))
        if ref.external_id:
            by_external_id[ref.external_id] = ref
        if ref.source_url:
            by_source_url[ref.source_url] = ref
    return by_external_id, by_source_url


def _needs_detail(
    candidate: Candidate,
    provider_slug: str,
    by_external_id: dict[str, ExistingRef],
    by_source_url: dict[str, ExistingRef],
) -> bool:
    existing = by_external_id.get(candidate.external_id) or by_source_url.get(candidate.source_url)
    if not existing:
        return True
    if provider_slug != "dou":
        return False
    candidate_seen_at = parse_timestamp(candidate.last_seen_at) or parse_timestamp(candidate.first_seen_at)
    if not candidate_seen_at or not existing.last_seen_at:
        return False
    return candidate_seen_at > existing.last_seen_at


def _is_duplicate(
    candidate: Candidate,
    by_external_id: dict[str, ExistingRef],
    by_source_url: dict[str, ExistingRef],
) -> bool:
    return candidate.external_id in by_external_id or candidate.source_url in by_source_url


def _build_payload(
    provider_slug: str,
    run_key: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    summary: str,
    blockers: list[str],
    metrics: FetchMetrics,
    candidates: list[Candidate],
) -> dict[str, Any]:
    source_items = [candidate.as_source_item(provider_slug) for candidate in candidates]
    opportunities = [candidate.as_opportunity(provider_slug) for candidate in candidates]
    payload = {
        "run": {
            "run_key": run_key,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "status": status,
            "summary": summary,
            "report_email_sent": False,
            "source_items_count": len(source_items),
            "opportunities_count": len(opportunities),
            "evaluations_count": 0,
            "manual_review_count": len(blockers),
            "metrics": metrics.to_dict(status),
        },
        "source_items": source_items,
        "opportunities": opportunities,
        "manual_review_blockers": [{"reason": blocker} for blocker in blockers],
        "summary": summary,
    }
    return payload


def _payload_path(provider_slug: str, run_key: str, payload_out: str | Path | None) -> Path | None:
    if payload_out:
        return Path(payload_out)
    return DEFAULT_OUTPUT_DIR / f"{provider_slug}-{run_key}.payload.json"


def _write_payload(path: Path | None, payload: dict[str, Any]) -> Path | None:
    if not path:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json(payload), encoding="utf-8")
    return path
