"""Calendar connector tests. All invites, people, and addresses are synthetic."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from jobtracker.calendar import ical as I
from jobtracker.calendar.events import (
    MANAGED_FOOTER,
    CalendarService,
    CalendarSettings,
    build_reply,
    ics_to_specs,
    key_to_uid,
    settings_from_options,
    spec_to_vevent,
    stored_spec,
    validate_spec,
)
from jobtracker.calendar.mail import classify_text, parse_message

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "profile/templates/generic/calendar"
SETTINGS = CalendarSettings(self_emails=frozenset({"candidate@example.com"}), cancel_prefix="Cancelled: ")

GOOGLE_REQUEST = """BEGIN:VCALENDAR\r
PRODID:-//Google Inc//Google Calendar 70.9054//EN\r
VERSION:2.0\r
METHOD:REQUEST\r
BEGIN:VTIMEZONE\r
TZID:Europe/Madrid\r
END:VTIMEZONE\r
BEGIN:VEVENT\r
DTSTART;TZID=Europe/Madrid:20301201T153000\r
DTEND;TZID=Europe/Madrid:20301201T161500\r
DTSTAMP:20301120T100000Z\r
ORGANIZER;CN=Recruiter One:mailto:recruiter@acme.example\r
UID:abc123@calendar.example\r
ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;CN=cand\r
 idate@example.com:mailto:candidate@example.com\r
ATTENDEE;PARTSTAT=ACCEPTED;CN=Recruiter One:mailto:recruiter@acme.example\r
X-GOOGLE-CONFERENCE:https://meet.google.com/abc-defg-hij\r
DESCRIPTION:Tech interview\\, round 1.\\n\\n-::~:~::~:~:~:~:~:~:~:~::~:~::-\\nJoin w\r
 ith Google Meet: https://meet.google.com/abc-defg-hij\r
SEQUENCE:0\r
STATUS:CONFIRMED\r
SUMMARY:Interview with Acme\r
END:VEVENT\r
END:VCALENDAR\r
"""

EXCHANGE_REQUEST = """BEGIN:VCALENDAR
METHOD:REQUEST
PRODID:Microsoft Exchange Server 2010
VERSION:2.0
BEGIN:VTIMEZONE
TZID:Romance Standard Time
BEGIN:STANDARD
DTSTART:16010101T030000
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
RRULE:FREQ=YEARLY;INTERVAL=1;BYDAY=-1SU;BYMONTH=10
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:16010101T020000
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
RRULE:FREQ=YEARLY;INTERVAL=1;BYDAY=-1SU;BYMONTH=3
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
ORGANIZER;CN=HR Person:mailto:hr@corp.example
ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:candidate@example.com
DESCRIPTION;LANGUAGE=en-US:Hello\\n____________________________________________\\nMicrosoft Teams \
meeting\\nhttps://teams.microsoft.com/l/meetup-join/19%3ameeting_X%40thread.v2/0?context=1
UID:040000008200E00074C5B7101A82E00800000000AA
SUMMARY;LANGUAGE=en-US:Screen | Candidate, Senior Dev
DTSTART;TZID=Romance Standard Time:20300304T093000
DTEND;TZID=Romance Standard Time:20300304T100000
SEQUENCE:3
DTSTAMP:20300225T180000Z
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR
"""

CUSTOM_TZ = EXCHANGE_REQUEST.replace("Romance Standard Time", "Custom Zone X")

GREENHOUSE_STYLE = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:icalendar-ruby
CALSCALE:GREGORIAN
BEGIN:VEVENT
DTSTAMP:20300709T144928Z
UID:a9b79806-7fe7-4775-a4ea-28306dd667a1
DTSTART;TZID=Europe/Berlin:20300710T133000
DTEND;TZID=Europe/Berlin:20300710T140000
DESCRIPTION:Join Zoom: https://corp.zoom.us/j/123456789?pwd=abc
LOCATION:
SUMMARY:Interview with Corp
END:VEVENT
END:VCALENDAR
"""

GENERIC_UID = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:linkedin.com
DTSTART:20300602T093000Z
DTEND:20300602T094500Z
SUMMARY:Interview with Someco
LOCATION:https://www.linkedin.com/hire/interview/xyz/details
END:VEVENT
END:VCALENDAR
"""

FLOATING = """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
BEGIN:VEVENT
UID:float-1
DTSTART:20300120T100000
DTEND:20300120T103000
SUMMARY:Office appointment
END:VEVENT
END:VCALENDAR
"""


def cancel_of(ics: str, seq: int = 1) -> str:
    return (
        ics.replace("METHOD:REQUEST", "METHOD:CANCEL")
        .replace("SEQUENCE:0", f"SEQUENCE:{seq}")
        .replace("STATUS:CONFIRMED", "STATUS:CANCELLED")
    )


def moved_invite() -> str:
    return (
        GOOGLE_REQUEST.replace("SEQUENCE:0", "SEQUENCE:2")
        .replace("T153000", "T170000")
        .replace("T161500", "T174500")
        .replace("DTSTAMP:20301120T100000Z", "DTSTAMP:20301121T100000Z")
    )


class FakeBackend:
    """In-memory backend implementing the CalendarBackend protocol."""

    slug = "fake"

    def __init__(self) -> None:
        self.objects: dict[str, tuple[str, str]] = {}
        self.n = 0
        self.full_scans = 0

    def calendars(self):
        from jobtracker.calendar.base import CalendarInfo

        return [CalendarInfo("Interviews", CAL)]

    def object_url(self, calendar_url, uid):
        return calendar_url + uid.replace("@", "_") + ".ics"

    def get(self, url):
        from jobtracker.calendar.base import CalendarObject

        if url not in self.objects:
            return None
        etag, data = self.objects[url]
        return CalendarObject(url, etag, data)

    def all_events(self, calendar_url):
        self.full_scans += 1
        return [self.get(url) for url in self.objects]

    def by_range(self, calendar_url, start, end):
        return [self.get(url) for url in self.objects]

    def put(self, url, ics, etag):
        if etag is None:
            assert url not in self.objects, "create must not overwrite"
        else:
            assert self.objects[url][0] == etag, "etag mismatch"
        self.n += 1
        self.objects[url] = (f'"{self.n}"', ics)
        return 201

    def delete(self, url, etag):
        del self.objects[url]

    def health(self):
        return []


CAL = "https://dav.example.com/123/calendars/interviews/"


class ParseTests(unittest.TestCase):
    def test_google_request(self) -> None:
        (s,) = ics_to_specs(GOOGLE_REQUEST, "imap://Jobs/1", settings=SETTINGS)
        self.assertEqual(s["action"], "upsert")
        self.assertEqual(s["key"], "invite:abc123@calendar.example")
        self.assertEqual(s["uid"], "abc123@calendar.example")
        self.assertEqual(s["start"], "2030-12-01T15:30:00+01:00")
        self.assertEqual(s["timezone"], "Europe/Madrid")
        self.assertTrue(s["timezone_confirmed"])
        self.assertEqual(s["meeting_url"], "https://meet.google.com/abc-defg-hij")
        self.assertEqual(s["notes"], "Tech interview, round 1.")
        self.assertEqual(s["source"]["my_partstat"], "NEEDS-ACTION")
        self.assertEqual(s["participants"], ["Recruiter One <recruiter@acme.example>"])
        self.assertEqual(validate_spec(s, SETTINGS), [])

    def test_exchange_windows_zone(self) -> None:
        (s,) = ics_to_specs(EXCHANGE_REQUEST, settings=SETTINGS)
        self.assertEqual(s["timezone"], "Europe/Paris")
        self.assertEqual(s["start"], "2030-03-04T09:30:00+01:00")
        self.assertTrue(s["meeting_url"].startswith("https://teams.microsoft.com/l/meetup-join/"))
        self.assertEqual(s["title"], "Screen | Candidate, Senior Dev")
        self.assertEqual(s["notes"], "Hello")
        self.assertEqual(s["source"]["sequence"], 3)

    def test_custom_zone_from_vtimezone(self) -> None:
        (s,) = ics_to_specs(CUSTOM_TZ)
        self.assertEqual(s["timezone"], "UTC")
        self.assertEqual(s["start"], "2030-03-04T08:30:00+00:00")
        summer = ics_to_specs(
            CUSTOM_TZ.replace("20300304T09", "20300704T09").replace("20300304T10", "20300704T10")
        )
        self.assertEqual(summer[0]["start"], "2030-07-04T07:30:00+00:00")

    def test_unknown_zone_uses_default_and_stays_unconfirmed(self) -> None:
        text = GREENHOUSE_STYLE.replace("TZID=Europe/Berlin", "TZID=Nowhere/Land")
        (s,) = ics_to_specs(text, default_tz="Europe/London")
        self.assertEqual(s["timezone"], "Europe/London")
        self.assertFalse(s["timezone_confirmed"])
        self.assertIn("unknown TZID", s["source"]["time_notes"])

    def test_cancel_and_reply(self) -> None:
        (c,) = ics_to_specs(cancel_of(GOOGLE_REQUEST))
        self.assertEqual((c["action"], c["status"]), ("cancel", "cancelled"))
        (r,) = ics_to_specs(GOOGLE_REQUEST.replace("METHOD:REQUEST", "METHOD:REPLY"))
        self.assertEqual(r["action"], "ignore")

    def test_no_method_ats_confirmation(self) -> None:
        (s,) = ics_to_specs(GREENHOUSE_STYLE)
        self.assertEqual(s["action"], "upsert")
        self.assertEqual(s["source"]["method"], "NONE")
        self.assertEqual(s["meeting_url"], "https://corp.zoom.us/j/123456789?pwd=abc")

    def test_generic_uid(self) -> None:
        (s,) = ics_to_specs(GENERIC_UID)
        self.assertTrue(s["key"].startswith("ics:"))
        self.assertIn("warning", s["source"])
        self.assertNotEqual(s["uid"], "linkedin.com")
        self.assertTrue(s["meeting_url"].startswith("https://www.linkedin.com/hire/interview/"))

    def test_duration_and_missing_end(self) -> None:
        with_duration = GENERIC_UID.replace("DTEND:20300602T094500Z", "DURATION:PT45M")
        (s,) = ics_to_specs(with_duration)
        self.assertEqual(s["end"], "2030-06-02T10:15:00+00:00")
        (s2,) = ics_to_specs(GENERIC_UID.replace("DTEND:20300602T094500Z\n", ""))
        self.assertIn("30 minutes assumed", s2["source"]["time_notes"])

    def test_floating_needs_zone(self) -> None:
        (s,) = ics_to_specs(FLOATING)
        self.assertFalse(s["timezone_confirmed"])
        self.assertTrue(validate_spec(s))
        (s2,) = ics_to_specs(FLOATING, default_tz="Europe/Madrid")
        self.assertEqual(validate_spec(s2), [])
        self.assertFalse(s2["timezone_confirmed"])

    def test_fold_escape_roundtrip(self) -> None:
        ev = I.Component("VEVENT")
        long = "Long description, with commas; semicolons and non-ASCII é ü ж\nand new lines " * 6
        ev.set("DESCRIPTION", I.escape(long))
        text = I.serialize(ev)
        self.assertTrue(all(len(line.encode()) <= 75 for line in text.split("\r\n")))
        self.assertEqual(I.unescape(I.parse_ical(text).value("DESCRIPTION")), long)

    def test_parse_errors_and_duration(self) -> None:
        with self.assertRaises(ValueError):
            I.parse_ical("not a calendar")
        self.assertIsNone(I.parse_duration("bogus"))
        self.assertEqual(I.parse_duration("P1DT2H").total_seconds(), 93600)

    def test_validate_spec_errors(self) -> None:
        errors = validate_spec({"action": "nope", "extra": 1})
        self.assertTrue(any("action" in e for e in errors))
        self.assertTrue(any("key" in e for e in errors))
        self.assertTrue(any("unknown fields" in e for e in errors))
        bad = {
            "action": "upsert",
            "key": "k",
            "title": "t",
            "start": "2030-01-01T10:00",
            "end": "2030-01-01T09:00",
        }
        self.assertIn("start has no offset: set timezone (IANA name)", validate_spec(bad))
        self.assertIn("end must be after start", validate_spec({**bad, "timezone": "UTC"}))
        self.assertTrue(any("unknown timezone" in e for e in validate_spec({**bad, "timezone": "Mars/Base"})))


class RenderTests(unittest.TestCase):
    def test_written_event_has_no_participants(self) -> None:
        (s,) = ics_to_specs(GOOGLE_REQUEST, settings=SETTINGS)
        ev = spec_to_vevent(s, None, 0, SETTINGS)
        names = {p.name for p in ev.props}
        self.assertNotIn("ORGANIZER", names)
        self.assertNotIn("ATTENDEE", names)
        self.assertEqual(ev.value("DTSTART"), "20301201T143000Z")
        self.assertEqual(ev.value("X-JOBSEARCH-KEY"), "invite:abc123@calendar.example")
        self.assertEqual(len(ev.sub("VALARM")), 2)
        description = I.unescape(ev.value("DESCRIPTION"))
        self.assertIn(MANAGED_FOOTER, description)
        self.assertIn("Organizer: Recruiter One <recruiter@acme.example>", description)

    def test_cancelled_rendering_uses_configured_prefix(self) -> None:
        (s,) = ics_to_specs(GOOGLE_REQUEST)
        s["status"] = "cancelled"
        settings = CalendarSettings(cancel_prefix="[x] ")
        ev = spec_to_vevent(s, None, 1, settings)
        self.assertTrue(I.unescape(ev.value("SUMMARY")).startswith("[x] "))
        self.assertEqual(ev.value("STATUS"), "CANCELLED")
        self.assertEqual(ev.value("TRANSP"), "TRANSPARENT")
        self.assertEqual(ev.sub("VALARM"), [])

    def test_all_day_rendering(self) -> None:
        spec = {"key": "manual:x", "uid": key_to_uid("manual:x"), "title": "Assessment due"}
        spec.update({"start": "2030-01-10", "end": "2030-01-11", "all_day": True, "status": "tentative"})
        ev = spec_to_vevent(spec, None, 0)
        self.assertEqual(ev.get("DTSTART").params, {"VALUE": "DATE"})
        self.assertEqual(ev.value("STATUS"), "TENTATIVE")

    def test_templates_validate(self) -> None:
        for name in ("event.json", "update.json", "cancel.json"):
            spec = json.loads((TEMPLATES / name).read_text(encoding="utf-8"))
            self.assertEqual(validate_spec(spec), [], name)

    def test_stored_spec_follows_time_moved_in_calendar_app(self) -> None:
        (s,) = ics_to_specs(GOOGLE_REQUEST)
        ev = spec_to_vevent(s, None, 0)
        ev.set("DTSTART", "20301201T180000Z")
        ev.set("DTEND", "20301201T184500Z")
        spec = stored_spec(ev)
        self.assertEqual(spec["start"], "2030-12-01T19:00:00+01:00")
        self.assertIn("time was changed in the calendar app", spec["history"])
        ev.set("X-JOBSEARCH-SPEC", "not base64!")
        self.assertIsNone(stored_spec(ev))


class ApplyFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = FakeBackend()
        self.service = CalendarService(self.backend, CAL, SETTINGS)

    def apply(self, spec, **kw):
        return self.service.apply(spec, **kw)

    def test_create_update_stale_cancel_delete(self) -> None:
        (s,) = ics_to_specs(GOOGLE_REQUEST, "imap://Jobs/1", settings=SETTINGS)
        r = self.apply(s)
        self.assertEqual((r["result"], r["verified"]), ("created", True))
        self.assertEqual(self.apply(s)["result"], "unchanged")
        (u,) = ics_to_specs(moved_invite(), "imap://Jobs/2", settings=SETTINGS)
        r = self.apply(u)
        self.assertEqual(r["result"], "updated")
        self.assertEqual(r["start_utc"], "20301201T160000Z")
        (old,) = ics_to_specs(GOOGLE_REQUEST.replace("SEQUENCE:0", "SEQUENCE:1"), "imap://Jobs/3")
        self.assertEqual(self.apply(old)["result"], "skipped")
        same_seq_older = moved_invite().replace("DTSTAMP:20301121T100000Z", "DTSTAMP:20301119T100000Z")
        (older,) = ics_to_specs(same_seq_older)
        self.assertIn("older DTSTAMP", self.apply(older)["reason"])
        (c,) = ics_to_specs(cancel_of(moved_invite(), seq=3), "imap://Jobs/4")
        self.assertEqual(self.apply(c)["result"], "cancelled")
        ((_, (_, ics)),) = self.backend.objects.items()
        ev = I.parse_ical(ics).sub("VEVENT")[0]
        self.assertEqual(ev.value("DTSTART"), "20301201T160000Z")  # cancellation keeps the latest time
        self.assertTrue(I.unescape(ev.value("SUMMARY")).startswith("Cancelled: "))
        self.assertIn("History:", I.unescape(ev.value("DESCRIPTION")))
        self.assertEqual(self.apply(c, dry_run=True, delete=True)["result"], "would_delete")
        self.assertEqual(self.apply(c, delete=True)["result"], "deleted")
        self.assertEqual(self.backend.objects, {})
        self.assertEqual(self.apply(c)["result"], "not_found")
        self.assertEqual(self.apply(c, delete=True)["result"], "not_found")

    def test_unmanaged_is_protected(self) -> None:
        foreign = GOOGLE_REQUEST.replace("METHOD:REQUEST\r\n", "")
        self.backend.objects[CAL + "x.ics"] = ('"e1"', foreign)
        (s,) = ics_to_specs(cancel_of(GOOGLE_REQUEST))
        self.assertEqual(self.apply(s)["result"], "unmanaged")
        self.assertEqual(self.apply(s, allow_unmanaged=True)["result"], "cancelled")

    def test_manual_spec_dry_run_and_reconfirm(self) -> None:
        spec = {
            "action": "upsert",
            "key": "manual:acme:video",
            "title": "Interview with Acme",
            "start": "2030-12-03T15:30",
            "end": "2030-12-03T16:15",
            "timezone": "Europe/Madrid",
            "timezone_confirmed": False,
            "meeting_url": "https://teams.microsoft.com/meet/1?p=x",
            "source": {"type": "email", "evidence": "imap://Jobs/9"},
        }
        r = self.apply(spec, dry_run=True)
        self.assertEqual(r["result"], "would_create")
        self.assertEqual(self.backend.objects, {})
        description = I.unescape(I.parse_ical(r["ics"]).sub("VEVENT")[0].value("DESCRIPTION"))
        self.assertIn("time zone not confirmed", description)
        self.assertEqual(self.apply(spec)["result"], "created")
        self.assertEqual(self.apply(spec)["result"], "unchanged")
        cancel = {"action": "cancel", "key": "manual:acme:video", "cancel_reason": "interviewer unavailable"}
        self.assertEqual(self.apply(cancel)["result"], "cancelled")
        found = self.service.find(key_to_uid("manual:acme:video"))
        patched = self.service.patch(found, start="2030-12-04T10:00", evidence="imap://Jobs/10")
        self.assertEqual(patched["status"], "confirmed")
        self.assertEqual(patched["title"], "Interview with Acme")
        self.assertEqual(patched["end"], "2030-12-04T10:45:00+01:00")  # duration kept
        r = self.apply(patched)
        self.assertEqual(r["result"], "updated")
        self.assertEqual(r["start_utc"], "20301204T090000Z")
        found = self.service.find(key_to_uid("manual:acme:video"))
        patched = self.service.patch(
            found, title="Final round", notes_append="Bring portfolio", timezone_name="UTC"
        )
        self.assertEqual(patched["timezone"], "UTC")
        self.assertIn("Bring portfolio", patched["notes"])

    def test_invalid_ignored_and_recurrence(self) -> None:
        self.assertEqual(self.apply({"action": "upsert"})["result"], "invalid")
        (reply,) = ics_to_specs(GOOGLE_REQUEST.replace("METHOD:REQUEST", "METHOD:REPLY"))
        self.assertEqual(self.apply(reply)["result"], "ignored")
        recurring = GOOGLE_REQUEST.replace("SEQUENCE:0", "RECURRENCE-ID:20301201T143000Z\r\nSEQUENCE:0")
        (s,) = ics_to_specs(recurring)
        self.assertEqual(self.apply(s)["result"], "manual")

    def test_lookup_avoids_full_scan_when_direct_get_hits(self) -> None:
        (s,) = ics_to_specs(GOOGLE_REQUEST)
        self.apply(s)
        scans = self.backend.full_scans
        self.assertIsNotNone(self.service.find(s["uid"]))
        self.assertEqual(self.backend.full_scans, scans)
        self.assertIsNone(self.service.find("missing@calendar.example"))
        self.assertEqual(self.backend.full_scans, scans + 1)

    def test_list_events_and_foreign_export(self) -> None:
        (s,) = ics_to_specs(GOOGLE_REQUEST)
        self.apply(s)
        self.backend.objects[CAL + "own.ics"] = ('"e2"', GREENHOUSE_STYLE)
        start, end = datetime(2030, 1, 1, tzinfo=timezone.utc), datetime(2031, 1, 1, tzinfo=timezone.utc)
        rows = self.service.list_events(start, end)
        self.assertEqual([row["managed"] for row in rows], [False, True])
        self.assertEqual(len(self.service.list_events(start, end, managed_only=True)), 1)
        self.assertEqual(len(self.service.list_events(start, end, grep="corp")), 1)
        found = self.service.find("a9b79806-7fe7-4775-a4ea-28306dd667a1")
        self.assertEqual(self.service.spec_of(found)["source"], {"type": "calendar"})


class SettingsTests(unittest.TestCase):
    def test_settings_from_options(self) -> None:
        settings = settings_from_options(
            {
                "calendar": "Work",
                "default_timezone": "Europe/London",
                "alarms_minutes": [30],
                "cancel_prefix": "",
                "text_rules": {"cancel_existing": ["annul"]},
            },
            {"JOBTRACKER_CALENDAR_SELF_EMAILS": "Me <me@own-domain.example>", "JOBTRACKER_IMAP_USER": ""},
        )
        self.assertEqual((settings.calendar, settings.alarms_minutes), ("Work", (30,)))
        self.assertTrue(settings.is_self("alias@own-domain.example"))
        self.assertFalse(settings.is_self(""))
        self.assertEqual(classify_text("Meeting annulled", "", settings), "cancel_existing")

    def test_public_domains_are_not_self(self) -> None:
        settings = settings_from_options({}, {"JOBTRACKER_IMAP_USER": "me@example.com"})
        self.assertTrue(settings.is_self("me@example.com"))
        self.assertFalse(settings.is_self("other@example.com"))

    def test_bad_settings(self) -> None:
        for options in (
            {"default_timezone": "Mars/Base"},
            {"alarms_minutes": "60"},
            {"text_rules": {"unknown": ["x"]}},
            {"text_rules": "x"},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                settings_from_options(options, {})


class MailTests(unittest.TestCase):
    def test_text_classification(self) -> None:
        self.assertEqual(classify_text("Interview Cancellation", ""), "cancel_existing")
        self.assertEqual(classify_text("Availability to Interview for 2nd Round", ""), "reply_to_recruiter")
        self.assertEqual(classify_text("Acme Interview Reminder", ""), "verify_existing")
        self.assertEqual(classify_text("Confirmation of video interview at Acme", ""), "manual_spec")
        self.assertEqual(classify_text("Rescheduling our chat", ""), "reschedule")
        self.assertEqual(classify_text("Your application at X", "Unfortunately..."), "none")
        self.assertEqual(classify_text("Hello", "we need to reschedule"), "reschedule")

    def test_message_with_duplicate_ics(self) -> None:
        msg = EmailMessage()
        msg["Subject"], msg["From"] = "Invitation: Interview with Acme", "recruiter@acme.example"
        msg.set_content("see invite")
        msg.add_alternative(GOOGLE_REQUEST, subtype="calendar", params={"method": "REQUEST"})
        msg.add_attachment(
            GOOGLE_REQUEST.encode(), maintype="application", subtype="ics", filename="invite.ics"
        )
        msg.add_attachment(b"", maintype="application", subtype="ics", filename="empty.ics")
        out = parse_message(msg.as_bytes(), "eml", None, SETTINGS)
        self.assertEqual(out["ics_parts"], 1)
        self.assertEqual(len(out["specs"]), 1)

    def test_text_only_message(self) -> None:
        msg = EmailMessage()
        msg["Subject"], msg["From"] = "Confirmation of your interview", "hr@corp.example"
        msg.set_content("Tuesday 10:00. Join: https://corp.zoom.us/j/987654321 .")
        msg.add_alternative("<p>Tuesday <b>10:00</b></p><style>p{}</style>", subtype="html")
        out = parse_message(msg.as_bytes(), "eml")
        self.assertEqual(out["suggested_action"], "manual_spec")
        self.assertEqual(out["meeting_urls"], ["https://corp.zoom.us/j/987654321"])
        self.assertIn("apply", out["next_step"])

    def test_build_reply(self) -> None:
        ics, to, subject, me = build_reply(GOOGLE_REQUEST, "ACCEPTED", None, SETTINGS)
        rep = I.parse_ical(ics)
        self.assertEqual(rep.value("METHOD"), "REPLY")
        (att,) = rep.sub("VEVENT")[0].all("ATTENDEE")
        self.assertEqual(att.params["PARTSTAT"], "ACCEPTED")
        self.assertEqual((to, me), ("recruiter@acme.example", "candidate@example.com"))
        self.assertEqual(subject, "Accepted: Interview with Acme")
        with self.assertRaises(ValueError):
            build_reply(GOOGLE_REQUEST, "ACCEPTED", "nobody@example.com")
        with self.assertRaises(ValueError):
            build_reply(GREENHOUSE_STYLE, "DECLINED", "candidate@example.com")
        with self.assertRaises(ValueError):
            build_reply(GOOGLE_REQUEST, "MAYBE", None, SETTINGS)


if __name__ == "__main__":
    unittest.main()
