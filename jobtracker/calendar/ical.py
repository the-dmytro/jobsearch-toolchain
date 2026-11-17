"""Minimal RFC 5545 parser/serializer and time-zone resolution (standard library only)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Windows (Exchange/Outlook) zone names that appear in invites, mapped to IANA names.
WINDOWS_TZ: dict[str, str] = {
    "Dateline Standard Time": "Etc/GMT+12",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "Alaskan Standard Time": "America/Anchorage",
    "Pacific Standard Time": "America/Los_Angeles",
    "Mountain Standard Time": "America/Denver",
    "US Mountain Standard Time": "America/Phoenix",
    "Central Standard Time": "America/Chicago",
    "Eastern Standard Time": "America/New_York",
    "Atlantic Standard Time": "America/Halifax",
    "SA Eastern Standard Time": "America/Cayenne",
    "E. South America Standard Time": "America/Sao_Paulo",
    "UTC": "UTC",
    "Coordinated Universal Time": "UTC",
    "GMT Standard Time": "Europe/London",
    "Greenwich Standard Time": "Atlantic/Reykjavik",
    "W. Europe Standard Time": "Europe/Berlin",
    "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw",
    "Romance Standard Time": "Europe/Paris",
    "GTB Standard Time": "Europe/Bucharest",
    "E. Europe Standard Time": "Europe/Chisinau",
    "FLE Standard Time": "Europe/Kyiv",
    "Israel Standard Time": "Asia/Jerusalem",
    "Turkey Standard Time": "Europe/Istanbul",
    "Russian Standard Time": "Europe/Moscow",
    "Arabian Standard Time": "Asia/Dubai",
    "India Standard Time": "Asia/Kolkata",
    "SE Asia Standard Time": "Asia/Bangkok",
    "China Standard Time": "Asia/Shanghai",
    "Singapore Standard Time": "Asia/Singapore",
    "Tokyo Standard Time": "Asia/Tokyo",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "New Zealand Standard Time": "Pacific/Auckland",
}
# Renamed IANA zones that older tz databases may only know under one of the names.
IANA_ALIASES: dict[str, str] = {"Europe/Kiev": "Europe/Kyiv", "Europe/Kyiv": "Europe/Kiev"}


@dataclass
class Prop:
    name: str
    params: dict[str, str]
    value: str


@dataclass
class Component:
    name: str
    props: list[Prop] = field(default_factory=list)
    children: list[Component] = field(default_factory=list)

    def get(self, name: str) -> Prop | None:
        return next((p for p in self.props if p.name == name), None)

    def value(self, name: str, default: str = "") -> str:
        prop = self.get(name)
        return prop.value if prop else default

    def all(self, name: str) -> list[Prop]:
        return [p for p in self.props if p.name == name]

    def set(self, name: str, value: str, params: dict[str, str] | None = None) -> None:
        self.remove(name)
        self.props.append(Prop(name, params or {}, value))

    def remove(self, name: str) -> None:
        self.props = [p for p in self.props if p.name != name]

    def sub(self, name: str) -> list[Component]:
        return [c for c in self.children if c.name == name]


def _split_params(head: str) -> tuple[str, dict[str, str]]:
    parts, cur, quoted = [], "", False
    for ch in head:
        if ch == '"':
            quoted = not quoted
        if ch == ";" and not quoted:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            params[key.upper()] = value.strip('"')
    return parts[0].upper(), params


def unfold(text: str) -> str:
    return re.sub(r"\r?\n[ \t]", "", text.replace("\r\n", "\n"))


def parse_ical(text: str) -> Component:
    root: Component | None = None
    stack: list[Component] = []
    for raw in unfold(text).split("\n"):
        if not raw.strip():
            continue
        quoted, colon = False, -1
        for i, ch in enumerate(raw):
            if ch == '"':
                quoted = not quoted
            elif ch == ":" and not quoted:
                colon = i
                break
        if colon < 0:
            continue
        name, params = _split_params(raw[:colon])
        value = raw[colon + 1 :]
        if name == "BEGIN":
            comp = Component(value.strip().upper())
            if stack:
                stack[-1].children.append(comp)
            else:
                root = comp
            stack.append(comp)
        elif name == "END":
            if stack:
                stack.pop()
        elif stack:
            stack[-1].props.append(Prop(name, params, value))
    if root is None:
        raise ValueError("no iCalendar component found")
    return root


def unescape(value: str) -> str:
    return re.sub(r"\\([\\;,nN])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), value)


def escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    out: list[str] = []
    cur = b""
    for ch in line:
        encoded = ch.encode()
        if len(cur) + len(encoded) > (75 if not out else 74):
            out.append(cur.decode())
            cur = b""
        cur += encoded
    out.append(cur.decode())
    return "\r\n ".join(out)


def _param(value: str) -> str:
    return f'"{value}"' if re.search(r"[:;,]", value) else value


def serialize(comp: Component) -> str:
    lines = [f"BEGIN:{comp.name}"]
    for prop in comp.props:
        params = "".join(f";{key}={_param(value)}" for key, value in prop.params.items())
        lines.append(_fold(f"{prop.name}{params}:{prop.value}"))
    for child in comp.children:
        lines.append(serialize(child).rstrip("\r\n"))
    lines.append(f"END:{comp.name}")
    return "\r\n".join(lines) + "\r\n"


# --------------------------------------------------------------------------- time zones

_WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def _nth_weekday(year: int, month: int, byday: str, hh: int, mm: int, ss: int) -> datetime:
    match = re.match(r"([+-]?\d)?(MO|TU|WE|TH|FR|SA|SU)", byday)
    if not match:
        raise ValueError(f"unsupported BYDAY {byday!r}")
    n = int(match.group(1) or 1)
    weekday = _WEEKDAYS.index(match.group(2))
    if n > 0:
        day = date(year, month, 1)
        day += timedelta(days=(weekday - day.weekday()) % 7 + 7 * (n - 1))
    else:
        nxt = date(year + (month == 12), month % 12 + 1, 1)
        day = nxt - timedelta(days=1)
        day -= timedelta(days=(day.weekday() - weekday) % 7 + 7 * (-n - 1))
    return datetime(day.year, day.month, day.day, hh, mm, ss)


def _offset(value: str) -> timedelta:
    sign = -1 if value.startswith("-") else 1
    value = value.lstrip("+-")
    return sign * timedelta(hours=int(value[:2]), minutes=int(value[2:4]), seconds=int(value[4:6] or 0))


def offset_from_vtimezone(vtz: Component, local: datetime) -> timedelta | None:
    """UTC offset at a local wall time from a VTIMEZONE's STANDARD/DAYLIGHT rules."""
    best: tuple[datetime, timedelta] | None = None
    for part in vtz.children:
        if part.name not in ("STANDARD", "DAYLIGHT") or not part.value("DTSTART"):
            continue
        start = datetime.strptime(part.value("DTSTART")[:15], "%Y%m%dT%H%M%S")
        to = _offset(part.value("TZOFFSETTO"))
        rule = dict(kv.split("=", 1) for kv in part.value("RRULE").split(";") if "=" in kv)
        candidates = [start]
        if rule.get("FREQ") == "YEARLY" and "BYMONTH" in rule and "BYDAY" in rule:
            for year in (local.year - 1, local.year):
                candidates.append(
                    _nth_weekday(
                        year, int(rule["BYMONTH"]), rule["BYDAY"], start.hour, start.minute, start.second
                    )
                )
        for candidate in candidates:
            if start <= candidate <= local and (best is None or candidate > best[0]):
                best = (candidate, to)
    return best[1] if best else None


def zone(name: str) -> ZoneInfo | None:
    for candidate in (name, IANA_ALIASES.get(name)):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return None


def resolve_tz(tzid: str, cal: Component | None = None) -> tuple[ZoneInfo | Component | None, str | None]:
    """Return ``(tzinfo or VTIMEZONE, iana_name_or_None)`` for a TZID parameter."""
    name = tzid.strip().strip('"')
    for candidate in (name, WINDOWS_TZ.get(name)):
        if not candidate:
            continue
        found = zone(candidate)
        if found is not None:
            return found, candidate
    if cal is not None:
        for vtz in cal.sub("VTIMEZONE"):
            if vtz.value("TZID").strip().strip('"') == name:
                return vtz, None
    return None, None


@dataclass
class When:
    value: datetime | date
    tz: str | None  # IANA name, "UTC", or None for floating / unresolved
    note: str = ""

    @property
    def all_day(self) -> bool:
        return not isinstance(self.value, datetime)


def parse_when(prop: Prop | None, cal: Component | None, default_tz: str | None = None) -> When | None:
    if prop is None or not prop.value:
        return None
    value = prop.value.strip()
    if prop.params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return When(datetime.strptime(value[:8], "%Y%m%d").date(), None)
    naive = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    if value.endswith("Z"):
        return When(naive.replace(tzinfo=timezone.utc), "UTC")
    tzid = prop.params.get("TZID")
    if tzid:
        tz, iana = resolve_tz(tzid, cal)
        if isinstance(tz, ZoneInfo):
            return When(naive.replace(tzinfo=tz), iana, "" if iana == tzid else f"source TZID '{tzid}'")
        if isinstance(tz, Component):
            off = offset_from_vtimezone(tz, naive)
            if off is not None:
                return When(
                    naive.replace(tzinfo=timezone(off)).astimezone(timezone.utc),
                    "UTC",
                    f"source TZID '{tzid}' resolved from its VTIMEZONE",
                )
        note = f"unknown TZID '{tzid}'"
    else:
        note = "floating time in source"
    default_zone = zone(default_tz) if default_tz else None
    if default_zone is not None:
        return When(naive.replace(tzinfo=default_zone), default_tz, note + f"; assumed {default_tz}")
    return When(naive, None, note)


def parse_duration(value: str) -> timedelta | None:
    match = re.fullmatch(
        r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value.strip()
    )
    if not match or not value.strip():
        return None
    weeks, days, hours, minutes, seconds = (int(x or 0) for x in match.groups()[1:])
    return timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes, seconds=seconds)


def to_utc_ical(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def aware(value: str, tz_name: str | None, default_tz: str = "UTC") -> datetime:
    """Parse an ISO datetime; naive values take ``tz_name`` (or the default zone)."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        tz: tzinfo | None = zone(tz_name or default_tz)
        if tz is None:
            raise ValueError(f"unknown time zone {tz_name or default_tz!r}")
        dt = dt.replace(tzinfo=tz)
    return dt
