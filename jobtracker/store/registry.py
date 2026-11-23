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


def canonical_backend(value: Any) -> str:
    backend = normalize_space(str(value or "")).lower()
    if not backend:
        raise MissingConfigurationError(
            'store.backend is not set: choose "sqlite" or "postgres" in config/jobsearch.toml.'
        )
    return "postgres" if backend in POSTGRES_ALIASES else backend


def postgres_transport(options: dict[str, Any]) -> str:
    transport = normalize_space(str(options.get("transport") or "")).lower()
    if transport not in {"direct", "supabase_https"}:
        raise MissingConfigurationError(
            'store.transport must be "direct" or "supabase_https" for the PostgreSQL store.'
        )
    return transport


@contextmanager
def connect_postgres(options: dict[str, Any]) -> Iterator[Any]:
    """Open the configured PostgreSQL transport. There is no automatic alternative."""
    if canonical_backend(options.get("backend")) != "postgres":
        raise MissingConfigurationError(
            f"This command needs the PostgreSQL store, but store.backend is {options.get('backend')!r}."
        )
    if postgres_transport(options) == "supabase_https":
        from .https_sql import connect_https

        with connect_https() as conn:
            yield conn
        return
    with connect() as conn:
        yield conn


def describe_store(options: dict[str, Any], *, root: Path) -> dict[str, Any]:
    """Human-checkable receipt of where data is written. Never includes credentials."""
    backend = canonical_backend(options.get("backend"))
    if backend == "sqlite":
        target = str(_resolved_path(root, options.get("sqlite_path") or "outputs/jobsearch.sqlite3"))
        return {"backend": "sqlite", "target": target, "shared": False}
    if backend == "postgres":
        transport = postgres_transport(options)
        if transport == "supabase_https":
            url = normalize_space(os.getenv("SUPABASE_URL")) if load_settings() else ""
            host = url.split("://", 1)[-1].split("/", 1)[0] if url else "unconfigured"
        else:
            host = _host_from_db_url(load_settings().db_url) or "unconfigured"
        return {"backend": "postgres", "transport": transport, "target": host, "shared": True}
    if backend == "memory":
        return {"backend": "memory", "target": "process memory", "shared": False}
    return {"backend": backend, "target": "plugin", "shared": None}


@contextmanager
def open_job_store(options: dict[str, Any], *, root: Path) -> Iterator[JobStore]:
    config = dict(options)
    backend = canonical_backend(config.get("backend"))
    if backend == "sqlite":
        db_path = _resolved_path(root, config.get("sqlite_path") or "outputs/jobsearch.sqlite3")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        yield SqliteJobStore(db_path)
        return
    if backend == "memory":
        yield MemoryJobStore()
        return
    if backend == "postgres":
        with connect_postgres(config) as conn:
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
    "connect_postgres",
    "describe_store",
    "open_job_store",
    "postgres_transport",
    "store_registry",
]
