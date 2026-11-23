from __future__ import annotations

import copy
import json
import os
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .app_config.profiles import JobboardProfile, load_profile
from .config import load_env_file
from .dedupe import LocalDedupeIndex, apply_db_dedupe_matches, dedupe_payload
from .provider_fetch import collect_provider_run
from .store.base import JobStore
from .utils import json_default, normalize_space, utc_now
from .validation import validate_payload

DEFAULT_JOBBOARD_PROVIDERS = ["dou", "workua", "djinni"]


def _report_email_to(profile: JobboardProfile) -> str | None:
    if profile.email_to:
        return profile.email_to
    load_env_file()
    return normalize_space(os.getenv("JOBTRACKER_REPORT_EMAIL_TO")) or None


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=json_default)


def _as_utc(value: datetime | None) -> datetime:
    now = value or utc_now()
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _payload_paths(output_dir: Path, date_slug: str, output_slug: str, provider: str) -> dict[str, Path]:
    prefix = f"{date_slug}-{output_slug}-{provider}"
    return {
        "payload": output_dir / f"{prefix}.payload.json",
        "normalized": output_dir / f"{prefix}.normalized.payload.json",
        "deduped": output_dir / f"{prefix}.deduped.payload.json",
    }


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json(payload), encoding="utf-8")


def _annotate_payload(
    payload: dict[str, Any], profile: JobboardProfile, provider: str, targets_path: Path
) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    metadata = result.setdefault("metadata", {})
    metadata["jobboard_profile"] = {
        "slug": profile.slug,
        "name": profile.name,
        "provider": provider,
        "targets_path": str(targets_path),
    }
    return result


def _store_dedupe(
    payload: dict[str, Any], provider: str, store: JobStore | None, run_key: str
) -> dict[str, Any]:
    if store is None:
        return payload
    matches_by_external_id: dict[str, list[dict[str, Any]]] = {}
    for item in payload.get("opportunities") or []:
        if not isinstance(item, dict):
            continue
        external_id = normalize_space(item.get("external_id"))
        matches = [
            match.as_dict()
            for match in store.check_duplicates(
                provider,
                item.get("company"),
                item.get("title"),
                external_id=external_id,
            )
        ]
        if external_id and matches:
            matches_by_external_id[external_id] = matches
    return apply_db_dedupe_matches(payload, matches_by_external_id, exclude_run_keys=[run_key])


def _uses_local_index(store: JobStore | None) -> bool:
    """Local payload history is a dedupe source only when the store itself is local.

    With the shared PostgreSQL store, duplicates are decided by the database alone so
    every environment gets the same answer.
    """
    return getattr(store, "backend", None) != "postgres"


def prepare_jobboard_run(
    *,
    profile_slug: str,
    providers: list[str] | None = None,
    output_dir: str | Path = "outputs/automation-payloads",
    payload_dir: str | Path = "outputs/automation-payloads",
    profile_dir: str | Path = "profile",
    root: str | Path | None = None,
    store: JobStore | None = None,
    config_path: str | Path | None = None,
    include_db: bool = True,
    fixture_dir: str | Path | None = None,
    now: datetime | None = None,
    max_pages: int = 1,
    detail_limit: int | None = None,
) -> dict[str, Any]:
    profile_key = normalize_space(profile_slug).lower()
    profile = load_profile(profile_key, profile_dir=profile_dir)
    provider_list = [
        normalize_space(provider).lower()
        for provider in (providers or DEFAULT_JOBBOARD_PROVIDERS)
        if normalize_space(provider)
    ]
    project_root = Path(root or Path.cwd())
    output_root = Path(output_dir)
    if not output_root.is_absolute():
        output_root = project_root / output_root
    payload_root = Path(payload_dir)
    if not payload_root.is_absolute():
        payload_root = project_root / payload_root
    output_root.mkdir(parents=True, exist_ok=True)
    started_at = _as_utc(now)
    date_slug = started_at.date().isoformat()
    targets_path = profile.targets_path
    manifest_run_key = f"{profile.output_slug}-{date_slug}"

    provider_runs: list[dict[str, Any]] = []
    overall_status = "completed"
    with ExitStack():
        conn = getattr(store, "conn", None) if store is not None else None
        if store is not None:
            db_status = {"status": "available", "backend": getattr(store, "backend", type(store).__name__)}
        else:
            if include_db:
                raise ValueError("include_db requires the configured store; open it with open_job_store")
            db_status = {"status": "skipped", "reason": "--no-db"}
        for provider in provider_list:
            provider_slug = normalize_space(provider).lower()
            paths = _payload_paths(output_root, date_slug, profile.output_slug, provider_slug)
            result = collect_provider_run(
                provider_slug,
                conn=conn,
                dry_run=True,
                payload_out=paths["payload"],
                fixture_dir=fixture_dir,
                targets_path=targets_path,
                config_path=config_path,
                root=project_root,
                run_key=f"{provider_slug}-{profile.output_slug}-{date_slug}",
                now=started_at,
                max_pages=max_pages,
                detail_limit=detail_limit,
            )
            raw_payload = _annotate_payload(result.payload, profile, provider_slug, targets_path)
            _write_payload(paths["payload"], raw_payload)

            validation = validate_payload(raw_payload, provider=provider_slug)
            if validation.errors:
                raise ValueError(f"{provider_slug} payload validation failed: {'; '.join(validation.errors)}")
            _write_payload(paths["normalized"], validation.normalized)

            if _uses_local_index(store):
                index = LocalDedupeIndex.from_payload_dir(
                    payload_root,
                    now=started_at,
                    exclude_paths=[paths["payload"], paths["normalized"], paths["deduped"]],
                    exclude_run_keys=[result.run_key],
                )
                deduped = dedupe_payload(validation.normalized, provider=provider_slug, index=index)
            else:
                deduped = copy.deepcopy(validation.normalized)
            deduped = _store_dedupe(deduped, provider_slug, store, result.run_key)
            _write_payload(paths["deduped"], deduped)

            if result.status != "completed":
                overall_status = "partial"
            provider_runs.append(
                {
                    "provider": provider_slug,
                    "run_key": result.run_key,
                    "status": result.status,
                    "summary": result.summary,
                    "payload_path": str(paths["payload"]),
                    "normalized_payload_path": str(paths["normalized"]),
                    "deduped_payload_path": str(paths["deduped"]),
                    "opportunities": len(deduped.get("opportunities") or []),
                    "source_items": len(deduped.get("source_items") or []),
                    "manual_review_blockers": result.blockers,
                    "metrics": result.metrics.to_dict(result.status),
                }
            )

    finished_at = _as_utc(now)
    report_path_value = Path(profile.report_path_template.format(date=date_slug))
    report_path = report_path_value if report_path_value.is_absolute() else project_root / report_path_value
    email_body_value = Path(profile.email_body_template.format(date=date_slug))
    email_body_path = email_body_value if email_body_value.is_absolute() else project_root / email_body_value
    manifest_path = output_root / f"{date_slug}-{profile.output_slug}-manifest.json"
    manifest = {
        "schema": "jobboard_automation_manifest_v1",
        "manifest_path": str(manifest_path),
        "profile": {
            "slug": profile.slug,
            "name": profile.name,
            "targets_path": str(targets_path),
            "profile_files": list(profile.profile_files),
            "evaluation_notes": list(profile.evaluation_notes),
        },
        "providers": provider_list,
        "run": {
            "run_key": manifest_run_key,
            "status": overall_status,
            "date": date_slug,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "summary": f"Prepared {sum(item['opportunities'] for item in provider_runs)} {profile.name} jobboard opportunities across {len(provider_runs)} providers.",
        },
        "db": db_status,
        "artifacts": {
            "report_path": str(report_path),
            "email_body_path": str(email_body_path),
        },
        "provider_runs": provider_runs,
        "deterministic_steps_completed": [
            "provider listing/detail fetch",
            "payload validation and normalization",
            "local payload-history dedupe (local stores only)",
            "configured-store duplicate check",
            "manifest and payload artifact writing",
        ],
        "llm_steps_remaining": [
            "read listed profile files",
            "evaluate and rank opportunities",
            "write evaluated payload JSON files using the deduped payloads as input",
            "write Markdown report",
            "write concise email body",
            "validate/upsert evaluated payloads with the report",
            "send one report email and upsert final sent state",
        ],
        "email": {
            "to": _report_email_to(profile),
            "subject_prefix": profile.email_subject_prefix,
        },
    }
    manifest_path.write_text(_json(manifest), encoding="utf-8")
    return manifest
