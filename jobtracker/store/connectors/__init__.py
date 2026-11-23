"""Database connectors: how the toolchain reaches a database.

A connector knows one access path to one kind of database (for example the
PostgreSQL wire protocol to any host, or Supabase's HTTPS API). Every connector
returns a connection with the same small DB-API surface, so stores and higher
layers do not care which one is configured. The config selects exactly one
connector per environment; connectors never stand in for each other.
"""

from .base import ConnectionLike, ConnectorInfo, DatabaseConnector, ProbeResult
from .registry import connector_registry, get_connector, list_connectors

__all__ = [
    "ConnectionLike",
    "ConnectorInfo",
    "DatabaseConnector",
    "ProbeResult",
    "connector_registry",
    "get_connector",
    "list_connectors",
]
