from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from jobtracker.core.models import CollectionContext, CollectionResult, FetchMetrics
from jobtracker.payloads import upsert_run_payload
from jobtracker.sources.base import JobSource
from jobtracker.sources.shared.fetch import FIXTURE_ROOT, FixtureFetcher, LiveFetcher
from jobtracker.sources.shared.payload import _build_payload, _json, _payload_path, _write_payload
from jobtracker.utils import normalize_space, slugify, utc_now

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROFILE_TARGETS = _REPO_ROOT / "profile" / "provider_targets.toml"
_FIXTURE_TARGETS = Path(__file__).resolve().parents[1] / "fixtures" / "provider_targets.toml"
TARGETS_PATH = _PROFILE_TARGETS if _PROFILE_TARGETS.exists() else _FIXTURE_TARGETS

source_registry: dict[str, JobSource] = {}

T = TypeVar("T", bound=type)


def register_source(cls: T) -> T:
    instance = cls()
    source_registry[instance.slug] = instance
    return cls


def _load_targets(path: str | Path | None = None) -> dict[str, Any]:
    target_path = Path(path or os.getenv("JOBTRACKER_PROVIDER_TARGETS") or TARGETS_PATH)
    return tomllib.loads(target_path.read_text(encoding="utf-8"))


def collect_provider_run(
    provider_slug: str,
    *,
    conn: Any | None = None,
    dry_run: bool,
    payload_out: str | Path | None = None,
    fixture_dir: str | Path | None = None,
    targets_path: str | Path | None = None,
    run_key: str | None = None,
    now: datetime | None = None,
    max_pages: int = 1,
    detail_limit: int | None = None,
    board_tokens: list[str] | None = None,
    max_boards: int | None = None,
) -> CollectionResult:
    provider_slug = slugify(provider_slug)
    targets = _load_targets(targets_path)
    metrics = FetchMetrics()
    started_at = now or utc_now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    provider_targets = targets["providers"].get(provider_slug) or {}
    resolved_detail_limit = detail_limit if detail_limit is not None else int(provider_targets.get("default_detail_limit") or 10)
    resolved_max_boards = max_boards if max_boards is not None else int((targets["providers"].get("greenhouse") or {}).get("default_max_boards") or 10)
    fetcher = FixtureFetcher(fixture_dir, metrics) if fixture_dir else LiveFetcher(metrics)
    source = source_registry.get(provider_slug)
    if not source:
        raise ValueError(f"Unsupported provider collector: {provider_slug}")
    ctx = CollectionContext(
        conn=conn,
        fetcher=fetcher,
        targets=targets,
        metrics=metrics,
        provider_slug=provider_slug,
        options={
            "detail_limit": resolved_detail_limit,
            "max_pages": max_pages,
            "board_tokens": board_tokens,
            "max_boards": resolved_max_boards,
        },
    )
    try:
        candidates, status, blockers = source.discover(ctx)
    finally:
        fetcher.close()

    finished_at = now or utc_now()
    if finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=timezone.utc)
    run_key = normalize_space(run_key) or f"{provider_slug}-discovery-{started_at.strftime('%Y%m%dT%H%M%SZ')}"
    lane_name = normalize_space((targets.get("role_lane") or {}).get("name")) or "target"
    summary = (
        f"{provider_slug} discovered {metrics.jobs_discovered} {lane_name} jobs; "
        f"emitted {len(candidates)}, skipped {metrics.jobs_skipped_as_duplicates} duplicates, "
        f"{metrics.request_count} requests."
    )
    if blockers:
        summary += f" Blockers: {' | '.join(blockers)}"
    payload = _build_payload(provider_slug, run_key, started_at, finished_at, status, summary, blockers, metrics, candidates)
    metrics.payload_size_bytes = len(_json(payload).encode("utf-8"))
    payload["run"]["metrics"] = metrics.to_dict(status)
    output_path = _payload_path(provider_slug, run_key, payload_out if dry_run and payload_out else payload_out)
    if not dry_run or payload_out:
        output_path = _write_payload(output_path, payload)
    else:
        output_path = None

    persisted = False
    persisted_result = None
    if not dry_run:
        if not output_path:
            output_path = _write_payload(_payload_path(provider_slug, run_key, None), payload)
        persisted_result = upsert_run_payload(conn, provider_slug, output_path)
        persisted = True

    return CollectionResult(
        provider_slug=provider_slug,
        candidates=candidates,
        status=status,
        summary=summary,
        blockers=blockers,
        metrics=metrics,
        run_key=run_key,
        payload=payload,
        payload_path=output_path,
        persisted=persisted,
        persisted_result=persisted_result,
    )


def benchmark_providers(
    providers: list[str],
    *,
    live: bool,
    fixture_dir: str | Path | None = None,
    now: datetime | None = None,
    max_pages: int = 1,
    detail_limit: int = 2,
    max_boards: int = 2,
) -> dict[str, Any]:
    results = []
    for provider in providers:
        try:
            result = collect_provider_run(
                provider,
                conn=None,
                dry_run=True,
                payload_out=None,
                fixture_dir=None if live else fixture_dir or FIXTURE_ROOT,
                now=now,
                max_pages=max_pages,
                detail_limit=detail_limit,
                max_boards=max_boards,
            )
            results.append(result.to_dict(dry_run=True))
        except Exception as exc:
            results.append(
                {
                    "provider": slugify(provider),
                    "dry_run": True,
                    "status": "partial",
                    "summary": f"{provider} benchmark failed: {exc}",
                    "run_key": None,
                    "payload_path": None,
                    "opportunities": 0,
                    "source_items": 0,
                    "blockers": [str(exc)],
                    "metrics": {"run_status": "partial"},
                    "persisted": False,
                    "persisted_result": None,
                }
            )
    return {"mode": "live" if live else "fixture", "results": results}


def _register_builtin_sources() -> None:
    from jobtracker.sources.services import ashby, djinni, dou, greenhouse, lever, workua  # noqa: F401


_register_builtin_sources()
