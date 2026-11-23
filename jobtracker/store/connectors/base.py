"""Contract shared by every database connector (DB-CONNECTOR-V1)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ConnectorInfo:
    """Static facts an agent uses to decide whether a connector fits an environment.

    ``dialect``: SQL dialect of the database (stores are written per dialect).
    ``network``: what must be reachable: ``"postgres_wire"`` (TCP to the database
    port) or ``"https"`` (an HTTPS API through ordinary web proxies).
    ``hosting``: ``"any"`` for a generic protocol, or the provider it is specific to.
    ``settings``: environment variable names the connector reads (never values).
    """

    name: str
    dialect: str
    network: str
    hosting: str
    transactional: bool
    settings: tuple[str, ...]
    secrets: tuple[str, ...]
    description: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProbeResult:
    """Outcome of a non-destructive reachability check.

    ``status``: ``available`` (a query succeeded), ``reachable`` (the endpoint answers
    but credentials or schema are missing), ``blocked`` (the network refuses),
    ``not_configured`` (settings are missing) or ``error``.
    """

    connector: str
    status: str
    evidence: list[str] = field(default_factory=list)
    needs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class CursorLike(Protocol):
    rowcount: int

    def __enter__(self) -> CursorLike: ...
    def __exit__(self, *exc: Any) -> Any: ...
    def execute(self, query: str, params: Any = None) -> Any: ...
    def fetchone(self) -> dict[str, Any] | None: ...
    def fetchall(self) -> list[dict[str, Any]]: ...


class ConnectionLike(Protocol):
    """The DB-API subset used by stores: dict rows, ``%s`` placeholders."""

    def cursor(self) -> CursorLike: ...
    def transaction(self) -> AbstractContextManager[Any]: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class DatabaseConnector(Protocol):
    info: ConnectorInfo

    def connect(self, options: dict[str, Any]) -> AbstractContextManager[ConnectionLike]: ...

    def target(self, options: dict[str, Any]) -> str:
        """Host or endpoint for receipts; never credentials."""
        ...

    def probe(self, options: dict[str, Any], *, timeout: float) -> ProbeResult: ...


def iter_settings_missing(names: tuple[str, ...], environ: dict[str, str]) -> Iterator[str]:
    for name in names:
        if not (environ.get(name) or "").strip():
            yield name
