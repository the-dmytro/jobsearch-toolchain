from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from jobtracker.config import load_settings
from jobtracker.core.connectors import ConnectorSpec
from jobtracker.core.models import ConnectorBuildContext
from jobtracker.core.registry import Registry
from jobtracker.db import MissingConfigurationError, _host_from_db_url, connect
from jobtracker.utils import normalize_space

from .base import JobStore
from .generic.memory import MemoryJobStore
from .generic.postgres import PostgresJobStore
from .generic.sqlite import SqliteJobStore

store_registry: Registry[Any] = Registry("store")


def _load_store_entry_point(entry_point: Any) -> ConnectorSpec:
    return ConnectorSpec(slug=entry_point.name, loaded=entry_point.load())


store_registry.load_entry_points("jobtracker.stores", entry_point_loader=_load_store_entry_point)


def _resolved_path(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


POSTGRES_ALIASES = frozenset({"postgres", "postgresql", "supabase"})
REQUIRED_STORE_ENV = "JOBTRACKER_REQUIRED_STORE"


def canonical_backend(value: Any) -> str:
    backend = normalize_space(str(value or "sqlite")).lower()
    return "postgres" if backend in POSTGRES_ALIASES else backend


def required_backend(options: dict[str, Any]) -> str | None:
    """Backend that writes must use, from ``store.required_backend`` or the environment."""
    load_settings()
    value = normalize_space(str(options.get("required_backend") or "")) or normalize_space(
        os.getenv(REQUIRED_STORE_ENV)
    )
    return canonical_backend(value) if value else None


def describe_store(options: dict[str, Any], *, root: Path) -> dict[str, Any]:
    """Human-checkable receipt of where data is written. Never includes credentials."""
    backend = canonical_backend(options.get("backend"))
    if backend == "sqlite":
        target = str(_resolved_path(root, options.get("sqlite_path") or "outputs/jobsearch.sqlite3"))
        return {"backend": "sqlite", "target": target, "shared": False}
    if backend == "postgres":
        host = _host_from_db_url(load_settings().db_url) or "unconfigured"
        return {"backend": "postgres", "target": host, "shared": True}
    if backend == "memory":
        return {"backend": "memory", "target": "process memory", "shared": False}
    return {"backend": backend, "target": "plugin", "shared": None}


def enforce_required_backend(options: dict[str, Any]) -> None:
    required = required_backend(options)
    if not required:
        return
    backend = canonical_backend(options.get("backend"))
    if backend != required:
        raise MissingConfigurationError(
            f"Refusing to use store backend {backend!r}: {required!r} is required "
            f"(store.required_backend or {REQUIRED_STORE_ENV}). Fix config/jobsearch.toml or use an "
            "explicit offline journal command instead of a silent local fallback."
        )


@contextmanager
def open_job_store(options: dict[str, Any], *, root: Path) -> Iterator[JobStore]:
    config = dict(options)
    enforce_required_backend(config)
    backend = str(config.get("backend") or "sqlite").strip().lower()
    if backend == "sqlite":
        db_path = _resolved_path(root, config.get("sqlite_path") or "outputs/jobsearch.sqlite3")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        yield SqliteJobStore(db_path)
        return
    if backend == "memory":
        yield MemoryJobStore()
        return
    if backend in {"postgres", "postgresql", "supabase"}:
        with connect() as conn:
            yield PostgresJobStore(conn, config)
        return
    item = store_registry.get(backend)
    if isinstance(item, ConnectorSpec):
        context = ConnectorBuildContext(root=root, slug=backend, options=config)
        yield item.build(context)
        return
    yield item


__all__ = [
    "canonical_backend",
    "describe_store",
    "enforce_required_backend",
    "open_job_store",
    "required_backend",
    "store_registry",
]
