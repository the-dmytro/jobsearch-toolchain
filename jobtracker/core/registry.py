from __future__ import annotations

from collections.abc import Callable, Iterable
from importlib.metadata import EntryPoint, entry_points
from typing import Generic, TypeVar, cast

from .errors import UnknownConnectorError

T = TypeVar("T")


class Registry(Generic[T]):
    def __init__(self, name: str = "connector") -> None:
        self._name = name
        self._items: dict[str, T] = {}

    def register(self, slug: str | T | None = None) -> Callable[[T], T] | T:
        def _store(resolved_slug: str, item: T) -> T:
            key = resolved_slug.strip().lower()
            if not key:
                raise ValueError(f"{self._name} slug is required")
            self._items[key] = item
            return item

        def decorator(item: T) -> T:
            resolved = slug if isinstance(slug, str) else getattr(item, "slug", None)
            if not resolved:
                raise ValueError(f"{self._name} slug is required when registering {item!r}")
            return _store(str(resolved), item)

        if callable(slug):
            return decorator(cast(T, slug))
        if slug is not None and not isinstance(slug, str):
            return decorator(cast(T, slug))
        return decorator

    def get(self, slug: str) -> T:
        key = slug.strip().lower()
        try:
            return self._items[key]
        except KeyError as exc:
            available = ", ".join(sorted(self._items)) or "(none)"
            raise UnknownConnectorError(f"Unknown {self._name} {slug!r}. Available: {available}") from exc

    def all(self) -> dict[str, T]:
        return dict(self._items)

    def load_entry_points(
        self, group: str, *, entry_point_loader: Callable[[EntryPoint], T] | None = None
    ) -> None:
        loader = entry_point_loader or (lambda entry_point: cast(T, entry_point.load()))
        for entry_point in _iter_entry_points(group):
            key = entry_point.name.strip().lower()
            if key in self._items:
                continue
            self._items[key] = loader(entry_point)


def _iter_entry_points(group: str) -> Iterable[EntryPoint]:
    discovered = entry_points(group=group)
    if hasattr(discovered, "select"):
        return discovered.select(group=group)
    return [entry_point for entry_point in discovered if entry_point.group == group]
