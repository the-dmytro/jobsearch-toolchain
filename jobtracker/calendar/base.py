from __future__ import annotations

from datetime import datetime, timedelta
from typing import NamedTuple, Protocol, runtime_checkable

from .ical import unfold


class CalendarInfo(NamedTuple):
    name: str
    url: str


class CalendarObject(NamedTuple):
    url: str
    etag: str
    data: str


@runtime_checkable
class CalendarBackend(Protocol):
    """Storage for iCalendar objects in named calendars (CONNECTOR-V1 ``jobtracker.calendars``)."""

    slug: str

    def calendars(self) -> list[CalendarInfo]: ...

    def object_url(self, calendar_url: str, uid: str) -> str: ...

    def get(self, url: str) -> CalendarObject | None: ...

    def by_range(self, calendar_url: str, start: datetime, end: datetime) -> list[CalendarObject]: ...

    def all_events(self, calendar_url: str) -> list[CalendarObject]: ...

    def put(self, url: str, ics: str, etag: str | None) -> int: ...

    def delete(self, url: str, etag: str | None) -> None: ...

    def health(self) -> list[str]: ...


def calendar_url(backend: CalendarBackend, name: str) -> str:
    resolver = getattr(backend, "calendar_url", None)
    if callable(resolver):
        return str(resolver(name))
    available = backend.calendars()
    for info in available:
        if info.name == name:
            return info.url
    names = ", ".join(sorted(info.name for info in available)) or "(none)"
    raise ValueError(f"calendar {name!r} not found. Available: {names}")


def _has_uid(data: str, uid: str) -> bool:
    return any(line.strip() == f"UID:{uid}" for line in unfold(data).split("\n"))


def find_by_uid(
    backend: CalendarBackend, cal_url: str, uid: str, around: datetime | None = None
) -> list[CalendarObject]:
    """Find objects by UID without a server-side UID filter.

    Some servers (iCloud among them) reject a CalDAV ``prop-filter`` text-match on UID with
    HTTP 412. The lookup therefore tries, in order: a direct GET of the object URL this tool
    writes, a time-range query around the expected start, and finally a full calendar scan.
    Backends with an efficient lookup may provide ``by_uid`` instead.
    """
    by_uid = getattr(backend, "by_uid", None)
    if callable(by_uid):
        return list(by_uid(cal_url, uid, around))
    direct_url = backend.object_url(cal_url, uid)
    direct = backend.get(direct_url)
    if direct and _has_uid(direct.data, uid):
        return [direct]
    if around is not None:
        hits = [
            item
            for item in backend.by_range(cal_url, around - timedelta(days=3), around + timedelta(days=3))
            if _has_uid(item.data, uid)
        ]
        if hits:
            return hits
    return [item for item in backend.all_events(cal_url) if _has_uid(item.data, uid)]
