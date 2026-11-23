from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..core.connectors import ConnectorSpec
from ..core.models import ConnectorBuildContext
from ..core.registry import Registry
from .base import CalendarBackend
from .generic.caldav import build_caldav_backend
from .generic.icsdir import build_icsdir_backend

BUILTIN_CALENDAR_KINDS = ("caldav", "icsdir")
calendar_registry: Registry[Any] = Registry("calendar backend")


def _load_entry_point(entry_point: Any) -> ConnectorSpec:
    return ConnectorSpec(slug=entry_point.name, loaded=entry_point.load())


calendar_registry.load_entry_points("jobtracker.calendars", entry_point_loader=_load_entry_point)


def build_calendar_backend(
    options: Mapping[str, Any], *, root: Path, env: Mapping[str, str] | None = None
) -> CalendarBackend:
    """Build the backend named by ``[calendar].kind``; built-ins win over plugins."""
    config = dict(options)
    kind = str(config.get("kind") or "caldav").strip().lower()
    environment = dict(env if env is not None else os.environ)
    if kind == "caldav":
        return build_caldav_backend(config, environment)
    if kind == "icsdir":
        return build_icsdir_backend(config, root)
    item = calendar_registry.get(kind)
    if isinstance(item, ConnectorSpec):
        return item.build(ConnectorBuildContext(root, kind, config))
    return item
