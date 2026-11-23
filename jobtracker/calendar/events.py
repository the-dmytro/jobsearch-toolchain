"""Event specs: iTIP classification, rendering, and managed create/update/cancel/delete.

A *spec* is a JSON-friendly dictionary describing one calendar event (see
``profile/templates/generic/calendar/``). Specs come from ``.ics`` invites (``ics_to_specs``)
or are written by hand for text-only e-mails, and are applied through a ``CalendarBackend``.

Safety rules:

* Written events never carry ORGANIZER/ATTENDEE, so a server never sends invitations or replies.
* Only events marked with ``X-JOBSEARCH-KEY`` ("managed") are changed unless explicitly allowed.
* An invite update with an older SEQUENCE (or the same SEQUENCE and an older DTSTAMP) is stale.
* Cancelling keeps the event (title prefix, STATUS:CANCELLED, alarms removed); deleting is explicit.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import uuid as uuidlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping

from .base import CalendarBackend, find_by_uid
from .ical import (
    Component,
    Prop,
    aware,
    escape,
    now_utc,
    parse_duration,
    parse_ical,
    parse_when,
    serialize,
    to_utc_ical,
    unescape,
    zone,
)

MANAGED_FOOTER = "jobsearch: managed event"
PRODID = "-//JobSearch Toolchain//jobtracker calendar//EN"
SPEC_FIELDS = (
    "action",
    "key",
    "uid",
    "title",
    "start",
    "end",
    "timezone",
    "timezone_confirmed",
    "all_day",
    "location",
    "meeting_url",
    "organizer",
    "participants",
    "notes",
    "status",
    "alarms_minutes",
    "source",
    "jobsearch",
    "history",
    "cancel_reason",
)
ACTIONS = ("upsert", "cancel", "delete", "ignore")
# UIDs that are not unique per event (some ATS exports use the sender's domain as UID).
GENERIC_UIDS = re.compile(r"^([\w-]+\.)+(com|io|net|org)$", re.I)
MEETING_URL = re.compile(
    r"https://(?:[\w-]+\.)?(?:teams\.microsoft\.com/(?:l/meetup-join|meet)/[^\s\"'<>]+"
    r"|zoom\.us/j/[^\s\"'<>]+|meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}[^\s\"'<>]*"
    r"|[\w-]+\.webex\.com/[^\s\"'<>]+|whereby\.com/[^\s\"'<>]+"
    r"|www\.linkedin\.com/hire/interview/[^\s\"'<>]+)",
    re.I,
)
PUBLIC_MAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "yahoo.com",
        "proton.me",
        "protonmail.com",
        "gmx.com",
        "gmx.net",
        "aol.com",
        "yandex.com",
        "example.com",
        "example.org",
        "example.net",
    }
)
# Text-only e-mail classification: first match on the subject wins, then on subject + body.
DEFAULT_TEXT_RULES: tuple[tuple[str, str], ...] = (
    ("cancel_existing", r"\bcancel(?:l?ed|lation)?\b|appointment cancelled"),
    ("reschedule", r"reschedul|moved to|new time|updated invitation"),
    (
        "reply_to_recruiter",
        r"availability|book a time|schedule your|select a time|choose a time|pick a time"
        r"|calendly|goodtime|modernloop|let us know when",
    ),
    ("verify_existing", r"\breminder\b|upcoming interview"),
    ("manual_spec", r"confirm|scheduled|invitation|invite|interview|\bcall\b"),
)
SELF_HINT_ENV = ("JOBTRACKER_IMAP_USER", "JOBTRACKER_SMTP_FROM", "JOBTRACKER_SMTP_USER")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+")


@dataclass(frozen=True)
class CalendarSettings:
    calendar: str = "Interviews"
    default_timezone: str = "UTC"
    alarms_minutes: tuple[int, ...] = (60, 15)
    cancel_prefix: str = "Cancelled: "
    self_emails: frozenset[str] = frozenset()
    text_rules: tuple[tuple[str, str], ...] = DEFAULT_TEXT_RULES
    public_mail_domains: frozenset[str] = field(default=PUBLIC_MAIL_DOMAINS)

    def is_self(self, address: str) -> bool:
        """The user's own address, or any address on the user's own (non-public) mail domain."""
        address = address.lower().strip()
        if not address:
            return False
        if address in self.self_emails:
            return True
        own_domains = {item.split("@")[-1] for item in self.self_emails} - self.public_mail_domains
        return address.split("@")[-1] in own_domains


def settings_from_options(options: Mapping[str, Any], env: Mapping[str, str]) -> CalendarSettings:
    """Build settings from the ``[calendar]`` TOML table and environment variables."""
    self_env = str(options.get("self_emails_env") or "JOBTRACKER_CALENDAR_SELF_EMAILS")
    emails: set[str] = set()
    for name in (self_env, *SELF_HINT_ENV):
        emails.update(match.group(0).lower() for match in EMAIL_RE.finditer(env.get(name, "")))
    default_tz = str(options.get("default_timezone") or "UTC")
    if zone(default_tz) is None:
        raise ValueError(f"calendar.default_timezone {default_tz!r} is not a known IANA zone")
    alarms = options.get("alarms_minutes", [60, 15])
    if not isinstance(alarms, list) or not all(isinstance(m, int) and m >= 0 for m in alarms):
        raise ValueError("calendar.alarms_minutes must be an array of non-negative integers")
    extra = options.get("text_rules") or {}
    if not isinstance(extra, Mapping):
        raise ValueError("calendar.text_rules must be a table of action = [patterns]")
    known = {name for name, _ in DEFAULT_TEXT_RULES}
    unknown = set(extra) - known
    if unknown:
        raise ValueError(
            f"calendar.text_rules has unknown actions: {', '.join(sorted(unknown))}; "
            f"use {', '.join(sorted(known))}"
        )
    rules = []
    for name, pattern in DEFAULT_TEXT_RULES:
        additions = [str(p) for p in (extra.get(name) or []) if str(p)]
        for addition in additions:
            re.compile(addition)
        rules.append((name, "|".join([pattern, *additions])))
    return CalendarSettings(
        calendar=str(options.get("calendar") or "Interviews"),
        default_timezone=default_tz,
        alarms_minutes=tuple(alarms),
        cancel_prefix=str(options.get("cancel_prefix", "Cancelled: ")),
        self_emails=frozenset(emails),
        text_rules=tuple(rules),
    )


def _today() -> date:
    return date.today()


# --------------------------------------------------------------------------- specs from iCalendar


def key_to_uid(key: str) -> str:
    if key.startswith("invite:"):
        return key[len("invite:") :]
    return "jobsearch-" + hashlib.sha1(key.encode()).hexdigest()[:20] + "@jobsearch.invalid"


def strip_boilerplate(text: str) -> str:
    text = html.unescape(re.sub(r"<br\s*/?>|</p>|</div>", "\n", text, flags=re.I))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.split(r"\n?-::~[:~]+", text)[0]  # Google Calendar invite footer
    text = re.split(r"_{20,}", text)[0]  # Microsoft Teams footer rule
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:1500]


def find_meeting_url(*texts: str) -> str:
    for text in texts:
        match = MEETING_URL.search(text or "")
        if match:
            return match.group(0).rstrip(".,)>")
    return ""


def addr(prop: Prop) -> tuple[str, str]:
    email = re.sub(r"^mailto:", "", prop.value, flags=re.I).strip()
    return prop.params.get("CN", "").strip(), email


def _person(prop: Prop) -> str:
    cn, email = addr(prop)
    return f"{cn} <{email}>" if cn and cn != email else email


def _iso(when: Any) -> str:
    if when.all_day:
        return when.value.isoformat()
    if when.tz and when.tz != "UTC":
        tz = zone(when.tz)
        return (when.value.astimezone(tz) if tz else when.value).isoformat()
    return when.value.isoformat()


def vevent_to_spec(
    ev: Component,
    cal: Component,
    method: str,
    evidence: str = "",
    default_tz: str | None = None,
    settings: CalendarSettings | None = None,
) -> dict[str, Any]:
    settings = settings or CalendarSettings()
    fallback_tz = default_tz or settings.default_timezone
    start = parse_when(ev.get("DTSTART"), cal, fallback_tz)
    end = parse_when(ev.get("DTEND"), cal, fallback_tz)
    time_notes = list(dict.fromkeys(w.note for w in (start, end) if w and w.note))
    if start and not end:
        duration = parse_duration(ev.value("DURATION"))
        if duration is None:
            duration = timedelta(days=1) if start.all_day else timedelta(minutes=30)
            if not start.all_day:
                time_notes.append("no end time in source; 30 minutes assumed")
        end = type(start)(start.value + duration, start.tz)
    uid = ev.value("UID").strip()
    generic_uid = not uid or bool(GENERIC_UIDS.match(uid))
    summary = unescape(ev.value("SUMMARY")).strip()
    desc_raw = unescape(ev.value("DESCRIPTION"))
    alt = ev.get("X-ALT-DESC")
    desc = strip_boilerplate(desc_raw or (unescape(alt.value) if alt else ""))
    location = unescape(ev.value("LOCATION")).strip()
    meeting = (
        ev.value("X-GOOGLE-CONFERENCE")
        or ev.value("X-MICROSOFT-SKYPETEAMSMEETINGURL")
        or find_meeting_url(location, desc_raw, ev.value("URL"), alt.value if alt else "")
    )
    organizer = ev.get("ORGANIZER")
    participants: list[str] = []
    my_status = None
    for attendee in ev.all("ATTENDEE"):
        _, email = addr(attendee)
        if settings.is_self(email):
            my_status = attendee.params.get("PARTSTAT", "NEEDS-ACTION")
            continue
        participants.append(_person(attendee))
    status = ev.value("STATUS", "CONFIRMED").upper()
    action = {"CANCEL": "cancel", "REPLY": "ignore"}.get(method, "upsert")
    if uid and not generic_uid:
        key = "invite:" + uid
    else:
        digest = hashlib.sha1(f"{uid}|{ev.value('DTSTART')}|{summary}".encode()).hexdigest()[:16]
        key = "ics:" + digest
    sequence_raw = ev.value("SEQUENCE") or "0"
    spec: dict[str, Any] = {
        "action": action,
        "key": key,
        "uid": key_to_uid(key),
        "title": summary,
        "start": _iso(start) if start else None,
        "end": _iso(end) if end else None,
        "timezone": start.tz if start else None,
        "timezone_confirmed": bool(start and start.tz and not start.note.startswith(("floating", "unknown"))),
        "all_day": bool(start and start.all_day),
        "location": "" if location == meeting else location,
        "meeting_url": meeting,
        "organizer": _person(organizer) if organizer else "",
        "participants": participants,
        "notes": desc,
        "status": "cancelled"
        if action == "cancel" or status == "CANCELLED"
        else ("tentative" if status == "TENTATIVE" else "confirmed"),
        "alarms_minutes": list(settings.alarms_minutes),
        "source": {
            "type": "ics",
            "evidence": evidence,
            "method": method or "NONE",
            "prodid": cal.value("PRODID"),
            "original_uid": uid,
            "sequence": int(sequence_raw) if sequence_raw.isdigit() else 0,
            "dtstamp": ev.value("DTSTAMP"),
            "recurrence_id": ev.value("RECURRENCE-ID") or None,
            "rrule": ev.value("RRULE") or None,
            "my_partstat": my_status,
            "time_notes": "; ".join(n for n in time_notes if n),
        },
        "jobsearch": {},
    }
    if generic_uid:
        spec["source"]["warning"] = (
            f"source UID '{uid}' is not unique; event keyed by content hash, "
            "later updates from the same sender will not match automatically"
        )
    return spec


def ics_to_specs(
    text: str,
    evidence: str = "",
    default_tz: str | None = None,
    settings: CalendarSettings | None = None,
) -> list[dict[str, Any]]:
    cal = parse_ical(text)
    method = cal.value("METHOD").strip().upper()
    return [vevent_to_spec(ev, cal, method, evidence, default_tz, settings) for ev in cal.sub("VEVENT")]


def _aware(value: str, spec: Mapping[str, Any], settings: CalendarSettings) -> datetime:
    return aware(value, spec.get("timezone"), settings.default_timezone)


def validate_spec(spec: Mapping[str, Any], settings: CalendarSettings | None = None) -> list[str]:
    settings = settings or CalendarSettings()
    errors: list[str] = []
    if spec.get("action") not in ACTIONS:
        errors.append("action must be upsert, cancel, delete or ignore")
    if not (spec.get("key") or spec.get("uid")):
        errors.append("key (or uid) is required")
    if spec.get("action") == "upsert":
        for name in ("title", "start", "end"):
            if not spec.get(name):
                errors.append(f"{name} is required for upsert")
        if spec.get("start") and not spec.get("all_day"):
            try:
                start = datetime.fromisoformat(str(spec["start"]).replace("Z", "+00:00"))
                if start.tzinfo is None and not spec.get("timezone"):
                    errors.append("start has no offset: set timezone (IANA name)")
                if spec.get("timezone") and zone(str(spec["timezone"])) is None:
                    errors.append(f"unknown timezone {spec['timezone']!r}")
                elif spec.get("end") and _aware(spec["end"], spec, settings) <= _aware(
                    spec["start"], spec, settings
                ):
                    errors.append("end must be after start")
            except ValueError as exc:
                errors.append(f"bad start/end/timezone: {exc}")
    unknown = set(spec) - set(SPEC_FIELDS) - {"$comment", "_comment"}
    if unknown:
        errors.append("unknown fields: " + ", ".join(sorted(unknown)))
    return errors


# --------------------------------------------------------------------------- rendering


def render_description(spec: Mapping[str, Any]) -> str:
    parts: list[str] = []
    if spec.get("notes"):
        parts.append(str(spec["notes"]).strip())
    if spec.get("meeting_url"):
        parts.append(f"Meeting: {spec['meeting_url']}")
    if spec.get("organizer"):
        parts.append(f"Organizer: {spec['organizer']}")
    if spec.get("participants"):
        parts.append("With: " + ", ".join(spec["participants"]))
    source = spec.get("source") or {}
    unconfirmed = not spec.get("timezone_confirmed", True)
    if unconfirmed or source.get("time_notes"):
        items = ["time zone not confirmed" if unconfirmed else "", source.get("time_notes", "")]
        parts.append("Time: " + "; ".join(x for x in items if x))
    if source.get("my_partstat"):
        parts.append(f"My response in the invite: {source['my_partstat']}")
    if spec.get("status") == "cancelled" and spec.get("cancel_reason"):
        parts.append(f"Cancelled: {spec['cancel_reason']}")
    history = spec.get("history") or []
    if history:
        parts.append("History:\n" + "\n".join(f"- {item}" for item in history[-8:]))
    if source.get("evidence"):
        parts.append(f"Source: {source['evidence']}")
    parts.append(f"— {MANAGED_FOOTER}; key={spec['key']}")
    return "\n\n".join(parts)


def spec_to_vevent(
    spec: Mapping[str, Any], created: str | None, sequence: int, settings: CalendarSettings | None = None
) -> Component:
    settings = settings or CalendarSettings()
    ev = Component("VEVENT")
    stamp = now_utc()
    ev.set("UID", spec["uid"])
    ev.set("DTSTAMP", stamp)
    ev.set("CREATED", created or stamp)
    ev.set("LAST-MODIFIED", stamp)
    ev.set("SEQUENCE", str(sequence))
    if spec.get("all_day"):
        ev.set("DTSTART", date.fromisoformat(str(spec["start"])[:10]).strftime("%Y%m%d"), {"VALUE": "DATE"})
        ev.set("DTEND", date.fromisoformat(str(spec["end"])[:10]).strftime("%Y%m%d"), {"VALUE": "DATE"})
    else:
        ev.set("DTSTART", to_utc_ical(_aware(spec["start"], spec, settings)))
        ev.set("DTEND", to_utc_ical(_aware(spec["end"], spec, settings)))
    title = str(spec["title"])
    cancelled = spec.get("status") == "cancelled"
    if cancelled and settings.cancel_prefix and not title.startswith(settings.cancel_prefix):
        title = settings.cancel_prefix + title
    ev.set("SUMMARY", escape(title))
    if spec.get("location") or spec.get("meeting_url"):
        ev.set("LOCATION", escape(spec.get("location") or spec["meeting_url"]))
    if spec.get("meeting_url"):
        ev.set("URL", spec["meeting_url"], {"VALUE": "URI"})
    ev.set("DESCRIPTION", escape(render_description(spec)))
    ev.set(
        "STATUS", {"cancelled": "CANCELLED", "tentative": "TENTATIVE"}.get(spec.get("status"), "CONFIRMED")
    )
    ev.set("TRANSP", "TRANSPARENT" if cancelled else "OPAQUE")
    ev.set("X-JOBSEARCH-KEY", spec["key"])
    source = spec.get("source") or {}
    ev.set("X-JOBSEARCH-SOURCE-SEQUENCE", str(source.get("sequence", 0)))
    if source.get("dtstamp"):
        ev.set("X-JOBSEARCH-SOURCE-DTSTAMP", source["dtstamp"])
    stored = {k: v for k, v in spec.items() if k != "action"}
    ev.set("X-JOBSEARCH-SPEC", base64.b64encode(json.dumps(stored, ensure_ascii=False).encode()).decode())
    if not cancelled:
        for minutes in spec.get("alarms_minutes") or []:
            alarm = Component("VALARM")
            alarm.set("ACTION", "DISPLAY")
            alarm.set("DESCRIPTION", "Reminder")
            alarm.set("TRIGGER", f"-PT{int(minutes)}M")
            alarm.set("UID", str(uuidlib.uuid4()).upper())
            ev.children.append(alarm)
    return ev


def wrap_calendar(ev: Component) -> str:
    cal = Component("VCALENDAR")
    cal.set("VERSION", "2.0")
    cal.set("PRODID", PRODID)
    cal.set("CALSCALE", "GREGORIAN")
    cal.children.append(ev)
    return serialize(cal)


def stored_spec(ev: Component, settings: CalendarSettings | None = None) -> dict[str, Any] | None:
    settings = settings or CalendarSettings()
    raw = ev.value("X-JOBSEARCH-SPEC")
    if not raw:
        return None
    try:
        spec = json.loads(base64.b64decode(raw).decode())
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(spec, dict):
        return None
    # The calendar wins over the stored copy for the time, which users may edit in a calendar app.
    cal = Component("VCALENDAR", children=[ev])
    start, end = parse_when(ev.get("DTSTART"), cal), parse_when(ev.get("DTEND"), cal)
    if start and not start.all_day and spec.get("start") and not spec.get("all_day"):
        try:
            moved = abs(start.value - _aware(spec["start"], spec, settings)) > timedelta(minutes=1)
        except (TypeError, ValueError):
            moved = False
        if moved:
            tz = zone(spec.get("timezone") or settings.default_timezone) or timezone.utc
            spec["start"] = start.value.astimezone(tz).isoformat()
            if end and not end.all_day:
                spec["end"] = end.value.astimezone(tz).isoformat()
            spec.setdefault("history", []).append("time was changed in the calendar app")
    return spec


# --------------------------------------------------------------------------- managed operations


@dataclass
class Found:
    url: str
    etag: str
    cal: Component
    event: Component

    @property
    def managed(self) -> bool:
        return bool(self.event.value("X-JOBSEARCH-KEY"))


def _same(name: str, a: Mapping[str, Any], b: Mapping[str, Any], settings: CalendarSettings) -> bool:
    if (
        name in ("start", "end")
        and a.get(name)
        and b.get(name)
        and not (a.get("all_day") or b.get("all_day"))
    ):
        try:
            return _aware(a[name], a, settings) == _aware(b[name], b, settings)
        except ValueError:
            pass
    return a.get(name) == b.get(name)


def _source_versions(spec: Mapping[str, Any], found: Found) -> tuple[int, int, str, str] | None:
    """``(new_seq, old_seq, new_stamp, old_stamp)`` for an invite-sourced spec, else ``None``."""
    source = spec.get("source") or {}
    if source.get("type") != "ics":
        return None
    stored_seq = found.event.value("X-JOBSEARCH-SOURCE-SEQUENCE")
    old_seq = int(stored_seq) if stored_seq.lstrip("-").isdigit() else -1
    new_seq = int(source.get("sequence") or 0)
    old_stamp = found.event.value("X-JOBSEARCH-SOURCE-DTSTAMP")
    new_stamp = str(source.get("dtstamp") or "")
    return new_seq, old_seq, new_stamp, old_stamp


def _source_newer(spec: Mapping[str, Any], found: Found) -> tuple[bool, str]:
    versions = _source_versions(spec, found)
    if versions is None:
        return True, ""
    new_seq, old_seq, new_stamp, old_stamp = versions
    if new_seq < old_seq:
        return False, f"stale: source SEQUENCE {new_seq} < stored {old_seq}"
    if new_seq == old_seq and old_stamp and new_stamp and new_stamp < old_stamp:
        return False, f"stale: same SEQUENCE and older DTSTAMP ({new_stamp} < {old_stamp})"
    return True, ""


def _source_advanced(spec: Mapping[str, Any], found: Found) -> bool:
    """True when the spec's invite version is strictly newer than the stored watermark."""
    versions = _source_versions(spec, found)
    if versions is None:
        return False
    new_seq, old_seq, new_stamp, old_stamp = versions
    return new_seq > old_seq or (new_seq == old_seq and bool(new_stamp) and new_stamp > old_stamp)


class CalendarService:
    """Managed event operations on one calendar of a backend."""

    def __init__(self, backend: CalendarBackend, cal_url: str, settings: CalendarSettings | None = None):
        self.backend = backend
        self.cal_url = cal_url
        self.settings = settings or CalendarSettings()

    # ---------------------------------------------------------------- lookup

    def find(self, uid: str, around: datetime | None = None) -> Found | None:
        for item in find_by_uid(self.backend, self.cal_url, uid, around):
            try:
                cal = parse_ical(item.data)
            except ValueError:
                continue
            events = cal.sub("VEVENT")
            masters = [e for e in events if not e.get("RECURRENCE-ID")] or events
            if masters and masters[0].value("UID").strip() == uid:
                return Found(item.url, item.etag, cal, masters[0])
        return None

    def spec_of(self, found: Found) -> dict[str, Any]:
        return stored_spec(found.event, self.settings) or self.foreign_spec(found)

    def foreign_spec(self, found: Found) -> dict[str, Any]:
        spec = vevent_to_spec(found.event, found.cal, "", "", self.settings.default_timezone, self.settings)
        spec["key"] = found.event.value("X-JOBSEARCH-KEY") or spec["key"]
        spec["uid"] = found.event.value("UID").strip()
        spec["source"] = {"type": "calendar"}
        return spec

    def list_events(
        self,
        start: datetime,
        end: datetime,
        *,
        grep: str | None = None,
        managed_only: bool = False,
    ) -> list[dict[str, Any]]:
        display = zone(self.settings.default_timezone) or timezone.utc
        rows: list[dict[str, Any]] = []
        for item in self.backend.by_range(self.cal_url, start, end):
            try:
                cal = parse_ical(item.data)
            except ValueError:
                continue
            for ev in cal.sub("VEVENT"):
                when = parse_when(ev.get("DTSTART"), cal, self.settings.default_timezone)
                if when is None:
                    start_local = ""
                elif when.all_day:
                    start_local = when.value.isoformat()
                else:
                    start_local = when.value.astimezone(display).isoformat(timespec="minutes")
                title = unescape(ev.value("SUMMARY"))
                row = {
                    "start_local": start_local,
                    "title": title,
                    "status": ev.value("STATUS", "CONFIRMED"),
                    "managed": bool(ev.value("X-JOBSEARCH-KEY")),
                    "key": ev.value("X-JOBSEARCH-KEY"),
                    "uid": ev.value("UID"),
                    "recurring": bool(ev.get("RRULE")),
                }
                if managed_only and not row["managed"]:
                    continue
                if grep and not re.search(grep, title + "\n" + unescape(ev.value("DESCRIPTION")), re.I):
                    continue
                rows.append(row)
        rows.sort(key=lambda r: r["start_local"])
        return rows

    # ---------------------------------------------------------------- writes

    def apply(
        self,
        spec: Mapping[str, Any],
        *,
        dry_run: bool = False,
        allow_unmanaged: bool = False,
        delete: bool = False,
    ) -> dict[str, Any]:
        settings = self.settings
        work: dict[str, Any] = dict(spec)
        work.setdefault("key", work.get("uid"))
        if work.get("key"):
            work["uid"] = work.get("uid") or key_to_uid(str(work["key"]))
        errors = validate_spec(work, settings)
        if errors:
            return {"result": "invalid", "errors": errors}
        action = "delete" if delete else work["action"]
        if action == "ignore":
            return {"result": "ignored", "reason": "iTIP REPLY or informational item; nothing to change"}
        if (work.get("source") or {}).get("recurrence_id"):
            return {
                "result": "manual",
                "reason": "update to one occurrence of a recurring event (RECURRENCE-ID); "
                "not supported, handle it in the calendar app",
            }
        if action != "delete" and (work.get("source") or {}).get("rrule"):
            return {
                "result": "manual",
                "reason": "recurring invite (RRULE); this tool writes single events only, "
                "handle the series in the calendar app",
            }
        around = None
        if work.get("start") and not work.get("all_day"):
            try:
                around = _aware(work["start"], work, settings)
            except ValueError:
                around = None
        found = self.find(work["uid"], around)
        if found and not found.managed and not allow_unmanaged:
            return {
                "result": "unmanaged",
                "url": found.url,
                "summary": unescape(found.event.value("SUMMARY")),
                "reason": "event exists but was not created by this tool; "
                "ask the user, then rerun with --allow-unmanaged",
            }
        if found and action != "delete" and (found.event.get("RRULE") or found.event.get("RDATE")):
            return {
                "result": "manual",
                "reason": "the calendar event is a recurring series; rewriting it would drop "
                "later occurrences, handle it in the calendar app",
                "url": found.url,
            }
        evidence = (work.get("source") or {}).get("evidence", "")
        if action == "delete":
            if not found:
                return {"result": "not_found", "uid": work["uid"]}
            if not dry_run:
                self.backend.delete(found.url, found.etag)
            return {"result": "would_delete" if dry_run else "deleted", "url": found.url}
        if action == "cancel":
            if not found:
                return {"result": "not_found", "uid": work["uid"], "reason": "nothing to cancel"}
            ok, why = _source_newer(work, found)
            if not ok:
                return {"result": "skipped", "reason": why}
            base = self.spec_of(found)
            base["status"] = "cancelled"
            base["cancel_reason"] = (
                work.get("cancel_reason") or work.get("notes") or "cancelled by the organizer"
            )
            base.setdefault("history", []).append(f"{_today()}: cancelled ({evidence})")
            if work.get("source"):
                base["source"] = {
                    **(base.get("source") or {}),
                    **{k: v for k, v in work["source"].items() if v},
                }
            work = base
        elif found:
            ok, why = _source_newer(work, found)
            if not ok:
                return {"result": "skipped", "reason": why}
            prev = stored_spec(found.event, settings) or {}
            changes = [
                name
                for name in ("title", "start", "end", "meeting_url", "location")
                if not _same(name, prev, work, settings)
            ]
            other = [
                name
                for name in (
                    "notes",
                    "status",
                    "organizer",
                    "participants",
                    "alarms_minutes",
                    "timezone_confirmed",
                )
                if prev.get(name) != work.get(name)
            ]
            # A newer invite version with identical details still advances the stored
            # SEQUENCE/DTSTAMP watermark, so an older invite arriving later stays stale.
            if found.managed and not changes and not other and not _source_advanced(work, found):
                return {"result": "unchanged", "url": found.url, "uid": work["uid"], "key": work["key"]}
            history = list(prev.get("history", []))
            if changes:
                history.append(f"{_today()}: updated {', '.join(changes)} ({evidence})")
            if prev.get("status") == "cancelled" and work.get("status") != "cancelled":
                history.append(f"{_today()}: re-confirmed after cancellation")
            work["history"] = history
            work.setdefault("jobsearch", prev.get("jobsearch", {}))
        created = found.event.value("CREATED") if found else None
        sequence = int(found.event.value("SEQUENCE") or 0) + 1 if found else 0
        ev = spec_to_vevent(work, created, sequence, settings)
        ics = wrap_calendar(ev)
        url = found.url if found else self.backend.object_url(self.cal_url, work["uid"])
        if not found:
            outcome = "created"
        elif work.get("status") == "cancelled":
            outcome = "cancelled"
        else:
            outcome = "updated"
        result: dict[str, Any] = {
            "result": outcome,
            "url": url,
            "uid": work["uid"],
            "key": work["key"],
            "title": unescape(ev.value("SUMMARY")),
            "start_utc": ev.value("DTSTART"),
        }
        if dry_run:
            result["result"] = (
                "would_" + {"created": "create", "updated": "update", "cancelled": "cancel"}[outcome]
            )
            result["ics"] = ics
            return result
        self.backend.put(url, ics, found.etag if found else None)
        back = self.find(work["uid"])
        result["verified"] = bool(
            back
            and back.event.value("SUMMARY") == ev.value("SUMMARY")
            and back.event.value("DTSTART") == ev.value("DTSTART")
        )
        return result

    def patch(
        self,
        found: Found,
        *,
        start: str | None = None,
        end: str | None = None,
        timezone_name: str | None = None,
        title: str | None = None,
        meeting_url: str | None = None,
        location: str | None = None,
        notes_append: str | None = None,
        evidence: str | None = None,
        reconfirm: bool = False,
    ) -> dict[str, Any]:
        """Return an upsert spec for one managed event with the given fields changed."""
        spec = self.spec_of(found)
        spec["action"] = "upsert"
        if timezone_name:
            spec["timezone"] = timezone_name
            spec["timezone_confirmed"] = True
        for name, value in (
            ("start", start),
            ("end", end),
            ("title", title),
            ("meeting_url", meeting_url),
            ("location", location),
        ):
            if value:
                spec[name] = value
        if start and not end and found.event.get("DTEND"):
            old_start = parse_when(found.event.get("DTSTART"), found.cal)
            old_end = parse_when(found.event.get("DTEND"), found.cal)
            if old_start and old_end and not old_start.all_day and not old_end.all_day:
                spec["end"] = (
                    _aware(start, spec, self.settings) + (old_end.value - old_start.value)
                ).isoformat()
        if notes_append:
            spec["notes"] = ((spec.get("notes") or "") + "\n" + notes_append).strip()
        if spec.get("status") == "cancelled" and (start or reconfirm):
            spec["status"] = "confirmed"
            prefix = self.settings.cancel_prefix
            if prefix and str(spec.get("title", "")).startswith(prefix):
                spec["title"] = str(spec["title"])[len(prefix) :]
        spec.setdefault("history", []).append(
            f"{_today()}: manual update ({evidence or 'no evidence given'})"
        )
        if evidence:
            spec["source"] = {**(spec.get("source") or {}), "type": "manual", "evidence": evidence}
        return spec


# --------------------------------------------------------------------------- iTIP REPLY

PARTSTAT_WORDS = {"ACCEPTED": "Accepted", "DECLINED": "Declined", "TENTATIVE": "Tentatively accepted"}


def build_reply(
    ics_text: str, partstat: str, me: str | None = None, settings: CalendarSettings | None = None
) -> tuple[str, str, str, str]:
    """Build an iTIP REPLY; returns ``(ics, organizer_email, subject, attendee_email)``."""
    settings = settings or CalendarSettings()
    if partstat not in PARTSTAT_WORDS:
        raise ValueError(f"partstat must be one of {', '.join(PARTSTAT_WORDS)}")
    cal = parse_ical(ics_text)
    events = cal.sub("VEVENT")
    if not events:
        raise ValueError("invite has no VEVENT")
    ev = events[0]
    organizer = ev.get("ORGANIZER")
    if not organizer:
        raise ValueError("invite has no ORGANIZER; nothing to reply to")
    mine = None
    for attendee in ev.all("ATTENDEE"):
        email = addr(attendee)[1].lower()
        if (email == me.lower()) if me else settings.is_self(email):
            mine = attendee
    if mine is None:
        raise ValueError("none of the attendees matches your address; pass --as EMAIL")
    reply = Component("VEVENT")
    for name in ("UID", "SEQUENCE", "DTSTART", "DTEND", "SUMMARY", "RECURRENCE-ID"):
        prop = ev.get(name)
        if prop:
            reply.props.append(Prop(prop.name, dict(prop.params), prop.value))
    reply.props.append(Prop("ORGANIZER", dict(organizer.params), organizer.value))
    params = {k: v for k, v in mine.params.items() if k == "CN"}
    params["PARTSTAT"] = partstat
    reply.props.append(Prop("ATTENDEE", params, mine.value))
    reply.set("DTSTAMP", now_utc())
    out = Component("VCALENDAR")
    out.set("VERSION", "2.0")
    out.set("PRODID", PRODID)
    out.set("METHOD", "REPLY")
    out.children += list(cal.sub("VTIMEZONE")) + [reply]
    subject = f"{PARTSTAT_WORDS[partstat]}: {unescape(ev.value('SUMMARY'))}"
    return serialize(out), addr(organizer)[1], subject, addr(mine)[1]
