"""CalDAV calendar backend (RFC 4791) using only the standard library."""

from __future__ import annotations

import base64
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..base import CalendarInfo, CalendarObject
from ..ical import to_utc_ical

NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
Transport = Callable[[urllib.request.Request, float], tuple[int, str, dict[str, str]]]


def _urlopen(request: urllib.request.Request, timeout: float) -> tuple[int, str, dict[str, str]]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace"), dict(response.headers)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, exc.read().decode("utf-8", "replace"), dict(exc.headers or {})
        finally:
            exc.close()


class CalDAVBackend:
    slug = "caldav"

    def __init__(
        self,
        url: str,
        user: str,
        password: str,
        *,
        calendar_url: str | None = None,
        timeout: float = 60.0,
        transport: Transport | None = None,
    ) -> None:
        if not url and not calendar_url:
            raise ValueError("calendar.url (CalDAV discovery root) or calendar.calendar_url is required")
        self.root = url or str(calendar_url)
        self.fixed_calendar_url = calendar_url
        self._auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self._has_credentials = bool(user and password)
        self.timeout = timeout
        self._transport = transport or _urlopen
        self._home: str | None = None

    # ------------------------------------------------------------------ HTTP

    def request(
        self, method: str, url: str, body: str | None = None, headers: dict[str, str] | None = None
    ) -> tuple[int, str, dict[str, str]]:
        merged = {"Authorization": self._auth, "Content-Type": "application/xml; charset=utf-8"}
        merged.update(headers or {})
        data = body.encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method, headers=merged)
        return self._transport(request, self.timeout)

    def _propfind(self, url: str, prop: str, depth: str) -> ET.Element:
        body = (
            '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            f"<d:prop>{prop}</d:prop></d:propfind>"
        )
        status, text, _ = self.request("PROPFIND", url, body, {"Depth": depth})
        if status != 207:
            raise RuntimeError(f"CalDAV PROPFIND returned {status}: login or discovery failed")
        return ET.fromstring(text)

    def home(self) -> str:
        if not self._home:
            tree = self._propfind(self.root, "<d:current-user-principal/>", "0")
            principal = tree.findtext(".//d:current-user-principal/d:href", "", NS)
            if not principal:
                raise RuntimeError("CalDAV server did not return current-user-principal")
            tree = self._propfind(urllib.parse.urljoin(self.root, principal), "<c:calendar-home-set/>", "0")
            home = tree.findtext(".//c:calendar-home-set/d:href", "", NS)
            if not home:
                raise RuntimeError("CalDAV server did not return calendar-home-set")
            self._home = urllib.parse.urljoin(self.root, home.strip())
        return self._home

    # ------------------------------------------------------------------ CalendarBackend

    def calendars(self) -> list[CalendarInfo]:
        home = self.home()
        tree = self._propfind(home, "<d:displayname/><d:resourcetype/>", "1")
        out: list[CalendarInfo] = []
        for response in tree.findall("d:response", NS):
            if response.find(".//d:resourcetype/c:calendar", NS) is None:
                continue
            name = response.findtext(".//d:displayname", "", NS)
            out.append(CalendarInfo(name, urllib.parse.urljoin(home, response.findtext("d:href", "", NS))))
        return out

    def object_url(self, calendar_url: str, uid: str) -> str:
        return calendar_url.rstrip("/") + "/" + re.sub(r"[^A-Za-z0-9._-]", "_", uid)[:120] + ".ics"

    def _report(self, calendar_url: str, flt: str) -> list[CalendarObject]:
        body = (
            '<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            "<d:prop><d:getetag/><c:calendar-data/></d:prop>"
            '<c:filter><c:comp-filter name="VCALENDAR">'
            f'<c:comp-filter name="VEVENT">{flt}</c:comp-filter>'
            "</c:comp-filter></c:filter></c:calendar-query>"
        )
        status, text, _ = self.request("REPORT", calendar_url, body, {"Depth": "1"})
        if status != 207:
            raise RuntimeError(f"CalDAV REPORT returned {status}")
        out: list[CalendarObject] = []
        for response in ET.fromstring(text).findall("d:response", NS):
            data = response.findtext(".//c:calendar-data", "", NS)
            if data:
                out.append(
                    CalendarObject(
                        urllib.parse.urljoin(calendar_url, response.findtext("d:href", "", NS)),
                        response.findtext(".//d:getetag", "", NS),
                        data,
                    )
                )
        return out

    def by_range(self, calendar_url: str, start: datetime, end: datetime) -> list[CalendarObject]:
        return self._report(
            calendar_url, f'<c:time-range start="{to_utc_ical(start)}" end="{to_utc_ical(end)}"/>'
        )

    def all_events(self, calendar_url: str) -> list[CalendarObject]:
        return self._report(calendar_url, "")

    def get(self, url: str) -> CalendarObject | None:
        status, text, headers = self.request("GET", url, None, {})
        if status != 200:
            return None
        etag = next((value for key, value in headers.items() if key.lower() == "etag"), "")
        return CalendarObject(url, etag, text)

    def put(self, url: str, ics: str, etag: str | None) -> int:
        headers = {"Content-Type": "text/calendar; charset=utf-8"}
        headers.update({"If-Match": etag} if etag else {"If-None-Match": "*"})
        status, text, _ = self.request("PUT", url, ics, headers)
        if status not in (200, 201, 204):
            raise RuntimeError(f"CalDAV PUT returned {status}: {text[:300]}")
        return status

    def delete(self, url: str, etag: str | None) -> None:
        status, text, _ = self.request("DELETE", url, None, {"If-Match": etag} if etag else {})
        if status not in (200, 204):
            raise RuntimeError(f"CalDAV DELETE returned {status}: {text[:300]}")

    def health(self) -> list[str]:
        if not self._has_credentials:
            return ["CalDAV user name or password is not set in the environment"]
        try:
            if self.fixed_calendar_url:
                return []
            self.home()
        except (RuntimeError, OSError, ET.ParseError) as exc:
            return [str(exc)]
        return []


def build_caldav_backend(options: dict[str, Any], env: dict[str, str]) -> CalDAVBackend:
    user_env = str(options.get("user_env") or "JOBTRACKER_CALDAV_USER")
    password_env = str(options.get("password_env") or "JOBTRACKER_CALDAV_PASSWORD")
    return CalDAVBackend(
        str(options.get("url") or ""),
        env.get(user_env, ""),
        env.get(password_env, ""),
        calendar_url=str(options.get("calendar_url") or "") or None,
        timeout=float(options.get("timeout_seconds") or 60),
    )
