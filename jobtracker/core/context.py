from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


class Fetcher(Protocol):
    def get_text(self, url: str, kind: str) -> str: ...

    def get_json(self, url: str, kind: str) -> Any: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class RoleLane:
    name: str
    include_terms: tuple[str, ...] = ()
    exclude_terms: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> RoleLane:
        lane = data or {}
        return cls(
            name=str(lane.get("name") or ""),
            include_terms=tuple(str(term) for term in (lane.get("include_terms") or [])),
            exclude_terms=tuple(str(term) for term in (lane.get("exclude_terms") or [])),
        )


@dataclass(frozen=True)
class RunLimits:
    max_pages: int = 1
    detail_limit: int = 10
    timeout: float = 20.0


@dataclass(frozen=True)
class HealthReport:
    slug: str
    status: str
    message: str
    blockers: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SourceContext:
    slug: str
    options: Mapping[str, Any]
    lane: RoleLane
    fetcher: Fetcher
    known_refs: frozenset[str]
    now: datetime
    limits: RunLimits
