from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from jobtracker.core.connectors import ConnectorSpec
from jobtracker.core.models import ConnectorBuildContext
from jobtracker.core.registry import Registry
from jobtracker.db import connect

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


@contextmanager
def open_job_store(options: dict[str, Any], *, root: Path) -> Iterator[JobStore]:
    config = dict(options)
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
            yield PostgresJobStore(conn)
        return
    item = store_registry.get(backend)
    if isinstance(item, ConnectorSpec):
        context = ConnectorBuildContext(root=root, slug=backend, options=config)
        yield item.build(context)
        return
    yield item


__all__ = ["open_job_store", "store_registry"]
