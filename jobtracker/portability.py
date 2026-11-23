"""Explicit offline journal, replay selection and post-run cleanup.

Rules:
- A write either lands in the configured shared store and is read back, or it is
  reported as ``pending_sync`` with a non-zero exit code. No silent local success.
- Local artifacts are removed only after the database holds their content.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from .app_config.loader import AppConfig
from .automation_state import AutomationStateStore
from .retention import apply_prune, candidate_files, classify, plan_prune, summarize
from .store.registry import canonical_backend
from .utils import normalize_space

DEFAULT_STATE_DB = Path("outputs/automation-state/state.sqlite")
PENDING_SYNC_EXIT_CODE = 3
KIND_PRIORITY = {"evaluated": 0, "deduped": 1, "raw": 2, "normalized": 3}


def state_db_path(root: Path, value: str | Path | None = None) -> Path:
    path = Path(value or DEFAULT_STATE_DB)
    return path if path.is_absolute() else root / path


def payload_run_key(payload: dict[str, Any]) -> str | None:
    run = payload.get("run") or {}
    return normalize_space(run.get("run_key") if isinstance(run, dict) else None) or normalize_space(
        payload.get("run_key")
    )


def journal_pending(
    state_db: Path, provider: str, payload_path: Path, error: str, run_key: str | None = None
) -> dict[str, Any]:
    if not run_key:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        run_key = payload_run_key(payload)
    if not run_key:
        raise ValueError(f"Cannot journal {payload_path}: payload has no run.run_key")
    state = AutomationStateStore(state_db)
    state.mark_run_sync_attempt(provider, run_key, str(payload_path), error=error)
    state.record_run_event(
        provider, run_key, "db_unavailable_journaled", error, {"payload_path": str(payload_path)}
    )
    return {"run_key": run_key, "provider": provider, "payload_path": str(payload_path)}


def choose_replay_files(paths: list[Path], journal: dict[str, str]) -> dict[str, Path]:
    """Pick one payload per run_key: the journaled file, else the most final variant."""
    grouped: dict[str, list[Path]] = {}
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        run_key = payload_run_key(payload) if isinstance(payload, dict) else None
        if run_key:
            grouped.setdefault(run_key, []).append(path)
    for run_key, journal_path in journal.items():
        path = Path(journal_path)
        if path.exists():
            grouped.setdefault(run_key, [])
            if path not in grouped[run_key]:
                grouped[run_key].append(path)
    chosen: dict[str, Path] = {}
    for run_key, candidates in grouped.items():
        journaled = journal.get(run_key)
        if journaled and Path(journaled).exists():
            chosen[run_key] = Path(journaled)
            continue
        candidates.sort(key=lambda item: (KIND_PRIORITY.get(classify(item), 9), -item.stat().st_mtime))
        chosen[run_key] = candidates[0]
    return chosen


def output_roots(config: AppConfig) -> list[Path]:
    roots = {config.resolve_path("outputs"), config.output_dir, config.payload_dir}
    for pipeline in config.pipelines.values():
        roots.add(config.resolve_path(pipeline["output_dir"]))
        roots.add(config.resolve_path(pipeline["payload_dir"]))
    return sorted(roots)


def report_dirs(config: AppConfig) -> list[Path]:
    return [config.resolve_path("outputs/reports")]


def require_shared_store(config: AppConfig) -> None:
    if canonical_backend(config.store.get("backend")) != "postgres":
        raise ValueError(
            "Refusing to prune: the configured store is not PostgreSQL, so local files are the only copy."
        )


def prune_local(
    config: AppConfig,
    store: Any,
    *,
    min_age_hours: float,
    apply: bool,
    paths: list[Path] | None = None,
) -> dict[str, Any]:
    require_shared_store(config)
    files = paths if paths is not None else candidate_files(output_roots(config), report_dirs(config))
    items = plan_prune(store, files, min_age=timedelta(hours=min_age_hours))
    result: dict[str, Any] = {
        "apply": apply,
        "min_age_hours": min_age_hours,
        "summary": summarize(items),
        "items": [item.as_dict() for item in items],
    }
    if apply:
        result["applied"] = apply_prune(items, stop_at=output_roots(config) + [config.root])
    return result


def prune_after_run(config: AppConfig, store: Any, manifest: dict[str, Any]) -> dict[str, Any]:
    """After a verified store write, drop this run's intermediates and old verified rounds."""
    if canonical_backend(config.store.get("backend")) != "postgres" or not config.store.get(
        "auto_prune", True
    ):
        return {"skipped": True, "reason": "auto_prune applies only to a PostgreSQL store"}
    current: list[Path] = []
    for provider_run in manifest.get("provider_runs") or []:
        for key in ("payload_path", "normalized_payload_path"):
            if provider_run.get(key):
                current.append(Path(provider_run[key]))
    now_items = prune_local(
        config, store, min_age_hours=0, apply=True, paths=[p for p in current if p.exists()]
    )
    older = prune_local(
        config,
        store,
        min_age_hours=float(config.store.get("prune_min_age_hours", 24)),
        apply=True,
    )
    return {
        "current_run": now_items.get("applied"),
        "older_rounds": older.get("applied"),
        "kept": older["summary"]["keep_count"],
    }
