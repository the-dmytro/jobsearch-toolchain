from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from jobtracker.core.connectors import ConnectorSpec
from jobtracker.core.models import ConnectorBuildContext
from jobtracker.core.registry import Registry
from jobtracker.db import MissingConfigurationError
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


def postgres_connector(options: dict[str, Any]) -> Any:
    """The single database connector named by ``store.connector``; checked against ``store.hosting``."""
    from .connectors import get_connector

    name = normalize_space(str(options.get("connector") or "")).lower()
    if not name:
        raise MissingConfigurationError(
            "No database connector selected: set JOBTRACKER_STORE_CONNECTOR in this environment "
            "(for example postgres_direct or supabase_https)."
        )
    connector = get_connector(name)
    hosting = normalize_space(str(options.get("hosting") or "")).lower()
    if hosting and connector.info.hosting not in {"any", hosting}:
        raise MissingConfigurationError(
            f"store.connector {name!r} only works with {connector.info.hosting!r} hosting, "
            f"but store.hosting is {hosting!r}."
        )
    if connector.info.dialect != "postgres":
        raise MissingConfigurationError(
            f"store.connector {name!r} speaks {connector.info.dialect!r}; the postgres store needs a postgres connector."
        )
    return connector


@contextmanager
def connect_postgres(options: dict[str, Any]) -> Iterator[Any]:
    """Open the one configured connector. There is no automatic alternative."""
    if canonical_backend(options.get("backend")) != "postgres":
        raise MissingConfigurationError(
            f"This command needs the PostgreSQL store, but store.backend is {options.get('backend')!r}."
        )
    with postgres_connector(options).connect(options) as conn:
        yield conn


def describe_store(options: dict[str, Any], *, root: Path) -> dict[str, Any]:
    """Human-checkable receipt of where data is written. Never includes credentials."""
    backend = canonical_backend(options.get("backend"))
    if backend == "sqlite":
        target = str(_resolved_path(root, options.get("sqlite_path") or "outputs/jobsearch.sqlite3"))
        return {"backend": "sqlite", "target": target, "shared": False}
    if backend == "postgres":
        connector = postgres_connector(options)
        receipt = {
            "backend": "postgres",
            "connector": connector.info.name,
            "target": connector.target(options),
            "shared": True,
        }
        if options.get("hosting"):
            receipt["hosting"] = options["hosting"]
        if options.get("connector_source"):
            receipt["selected_by"] = options["connector_source"]
        return receipt
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
    "postgres_connector",
    "store_registry",
]
