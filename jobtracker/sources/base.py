from __future__ import annotations

from typing import Protocol

from jobtracker.core.models import Candidate, CollectionContext


class JobSource(Protocol):
    slug: str

    def discover(self, ctx: CollectionContext) -> tuple[list[Candidate], str, list[str]]:
        ...

    def health(self, ctx: CollectionContext) -> list[str]:
        ...
