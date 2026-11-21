"""Offline calendar backend: one sub-directory per calendar, one ``.ics`` file per event."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..base import CalendarInfo, CalendarObject
from ..ical import parse_ical, parse_when


def _etag(data: str) -> str:
    return '"' + hashlib.sha256(data.encode()).hexdigest()[:16] + '"'


class IcsDirectoryBackend:
    slug = "icsdir"

    def __init__(self, path: Path) -> None:
        self.path = path

    def calendars(self) -> list[CalendarInfo]:
        if not self.path.is_dir():
            return []
        return [CalendarInfo(p.name, str(p)) for p in sorted(self.path.iterdir()) if p.is_dir()]

    def calendar_url(self, name: str) -> str:
        """Resolve (and create) the folder for a calendar name."""
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError(f"invalid calendar name {name!r}")
        folder = self.path / name
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)

    def object_url(self, calendar_url: str, uid: str) -> str:
        return str(Path(calendar_url) / (re.sub(r"[^A-Za-z0-9._-]", "_", uid)[:120] + ".ics"))

    def get(self, url: str) -> CalendarObject | None:
        path = Path(url)
        if not path.is_file():
            return None
        data = path.read_text(encoding="utf-8")
        return CalendarObject(url, _etag(data), data)

    def all_events(self, calendar_url: str) -> list[CalendarObject]:
        folder = Path(calendar_url)
        if not folder.is_dir():
            return []
        out = []
        for path in sorted(folder.glob("*.ics")):
            item = self.get(str(path))
            if item:
                out.append(item)
        return out

    def by_range(self, calendar_url: str, start: datetime, end: datetime) -> list[CalendarObject]:
        out = []
        for item in self.all_events(calendar_url):
            try:
                cal = parse_ical(item.data)
            except ValueError:
                continue
            for event in cal.sub("VEVENT"):
                when = parse_when(event.get("DTSTART"), cal, "UTC")
                if when is None:
                    continue
                if when.all_day:
                    moment = datetime(when.value.year, when.value.month, when.value.day, tzinfo=timezone.utc)
                else:
                    moment = when.value
                if start <= moment < end or event.get("RRULE"):
                    out.append(item)
                    break
        return out

    def put(self, url: str, ics: str, etag: str | None) -> int:
        path = Path(url)
        current = self.get(url)
        if etag is None and current is not None:
            raise RuntimeError(f"{path.name} already exists (If-None-Match failed)")
        if etag is not None and (current is None or current.etag != etag):
            raise RuntimeError(f"{path.name} changed since it was read (If-Match failed)")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ics, encoding="utf-8")
        return 201 if current is None else 204

    def delete(self, url: str, etag: str | None) -> None:
        current = self.get(url)
        if current is None:
            raise RuntimeError(f"{Path(url).name} does not exist")
        if etag is not None and current.etag != etag:
            raise RuntimeError(f"{Path(url).name} changed since it was read (If-Match failed)")
        Path(url).unlink()

    def health(self) -> list[str]:
        if self.path.exists() and not self.path.is_dir():
            return [f"calendar path is not a directory: {self.path}"]
        return []


def build_icsdir_backend(options: dict[str, Any], root: Path) -> IcsDirectoryBackend:
    raw = str(options.get("path") or "outputs/calendar")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = root / path
    return IcsDirectoryBackend(path)
