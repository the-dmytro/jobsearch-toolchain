"""Registry of database connectors: built-ins plus the ``jobtracker.db_connectors`` entry points."""

from __future__ import annotations

from typing import Any

from ...core.registry import Registry
from ...db import MissingConfigurationError
from .base import DatabaseConnector
from .postgres_direct import PostgresDirectConnector
from .supabase_https import SupabaseHttpsConnector

connector_registry: Registry[Any] = Registry("db_connector")
connector_registry.register("postgres_direct")(PostgresDirectConnector())
connector_registry.register("supabase_https")(SupabaseHttpsConnector())
connector_registry.load_entry_points("jobtracker.db_connectors")


def get_connector(name: str) -> DatabaseConnector:
    key = (name or "").strip().lower()
    if not key:
        raise MissingConfigurationError("store.connector is not set")
    try:
        item = connector_registry.get(key)
    except Exception as exc:
        available = ", ".join(sorted(connector_registry.all()))
        raise MissingConfigurationError(
            f"Unknown database connector {name!r}. Available: {available}"
        ) from exc
    return item() if isinstance(item, type) else item


def list_connectors() -> list[DatabaseConnector]:
    return [get_connector(name) for name in sorted(connector_registry.all())]
