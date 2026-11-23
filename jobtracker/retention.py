"""Remove local artifacts only after their content is verified in the shared database.

Nothing here deletes data that the database does not hold. When the configured store
is not PostgreSQL, local files are the only copy and pruning is refused.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .store.compact import sha256_json, sha256_text
from .utils import normalize_space

PAYLOAD_GLOBS = ("*.payload.json", "*-manifest.json", "*.source.json")
REPORT_SUFFIXES = (".md", ".txt")
PRE_FINAL_KINDS = frozenset({"raw", "normalized", "deduped", "manifest"})


@dataclass
class PruneItem:
    path: str
    kind: str
    action: str
    reason: str
    run_keys: list[str]
    size_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify(path: Path) -> str:
    name = path.name
    if name.endswith("-manifest.json"):
        return "manifest"
    if name.endswith(".source.json"):
        return "mail_source"
    if name.endswith(".normalized.payload.json"):
        return "normalized"
    if name.endswith(".deduped.payload.json"):
        return "deduped"
    if ".evaluated" in name or ".reviewed" in name:
        return "evaluated"
    if name.endswith(".payload.json"):
        return "raw"
    if path.suffix in REPORT_SUFFIXES:
        return "report"
    return "other"


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _run_keys(payload: dict[str, Any], kind: str) -> list[str]:
    if kind == "manifest":
        keys = [normalize_space(item.get("run_key")) for item in payload.get("provider_runs") or []]
        return [key for key in keys if key]
    run = payload.get("run") or {}
    key = normalize_space(run.get("run_key") if isinstance(run, dict) else None) or normalize_space(
        payload.get("run_key")
    )
    return [key] if key else []


def candidate_files(roots: list[Path], report_dirs: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for pattern in PAYLOAD_GLOBS:
            for path in root.rglob(pattern):
                resolved = path.resolve()
                if resolved not in seen and path.is_file():
                    seen.add(resolved)
                    files.append(path)
    for report_dir in report_dirs:
        if not report_dir.exists():
            continue
        for path in report_dir.rglob("*"):
            resolved = path.resolve()
            if path.is_file() and path.suffix in REPORT_SUFFIXES and resolved not in seen:
                seen.add(resolved)
                files.append(path)
    return sorted(files)


def plan_prune(
    store: Any,
    files: list[Path],
    *,
    min_age: timedelta,
    now: datetime | None = None,
) -> list[PruneItem]:
    current = now or datetime.now(timezone.utc)
    items: list[PruneItem] = []
    for path in files:
        kind = classify(path)
        size = path.stat().st_size
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

        def keep(reason: str, run_keys: list[str] | None = None) -> None:
            items.append(PruneItem(str(path), kind, "keep", reason, run_keys or [], size))

        def delete(reason: str, run_keys: list[str] | None = None) -> None:
            items.append(PruneItem(str(path), kind, "delete", reason, run_keys or [], size))

        if current - modified < min_age:
            keep(f"younger than {min_age}")
            continue

        if kind == "report":
            body = path.read_text(encoding="utf-8", errors="replace")
            document = store.find_document_by_sha(sha256_text(body))
            if document:
                delete(f"identical document {document['id']} stored")
            else:
                keep("no identical document in database; store it with `documents put` first")
            continue

        payload = _load_json(path)
        if payload is None:
            keep("not valid JSON; review manually")
            continue
        run_keys = _run_keys(payload, kind)
        if kind == "mail_source":
            keep("mail source export; state lives in the automation-state store, review manually", run_keys)
            continue
        if not run_keys:
            keep("no run_key; cannot verify against the database")
            continue
        stored = {key: store.verify_run(key) for key in run_keys}
        missing = [key for key, row in stored.items() if not row]
        if missing:
            keep(f"run not in database: {', '.join(missing)}; use upsert-run or sync-pending-runs", run_keys)
            continue
        if kind == "manifest":
            delete("all provider runs verified in database", run_keys)
            continue
        stored_sha = (stored[run_keys[0]] or {}).get("payload_sha256")
        if stored_sha and stored_sha == sha256_json(payload):
            delete("identical payload verified in database", run_keys)
        elif kind in PRE_FINAL_KINDS:
            delete("pre-final variant of a run that is verified in database", run_keys)
        else:
            keep("run exists but this content differs from the stored version; upsert it first", run_keys)
    return items


def apply_prune(items: list[PruneItem], *, stop_at: list[Path] | None = None) -> dict[str, Any]:
    deleted: list[str] = []
    freed = 0
    for item in items:
        if item.action != "delete":
            continue
        path = Path(item.path)
        if path.exists():
            path.unlink()
            deleted.append(item.path)
            freed += item.size_bytes
    boundaries = {path.resolve() for path in (stop_at or [])}
    for path_text in deleted:
        parent = Path(path_text).parent
        while parent.resolve() not in boundaries and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    return {"deleted": len(deleted), "freed_bytes": freed}


def summarize(items: list[PruneItem]) -> dict[str, Any]:
    delete = [item for item in items if item.action == "delete"]
    keep = [item for item in items if item.action == "keep"]
    return {
        "delete_count": len(delete),
        "delete_bytes": sum(item.size_bytes for item in delete),
        "keep_count": len(keep),
        "keep_bytes": sum(item.size_bytes for item in keep),
    }
