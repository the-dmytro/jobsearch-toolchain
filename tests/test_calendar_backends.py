"""Calendar backends, registry, config, and CLI. Offline: fake HTTP transport and temp dirs."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

from jobtracker import cli
from jobtracker.app_config.loader import load_app_config
from jobtracker.app_config.schema import ConfigValidationError
from jobtracker.calendar.base import CalendarBackend, calendar_url, find_by_uid
from jobtracker.calendar.generic.caldav import CalDAVBackend, build_caldav_backend
from jobtracker.calendar.generic.icsdir import IcsDirectoryBackend
from jobtracker.calendar.registry import build_calendar_backend
from jobtracker.calendar.reply import send_reply
from jobtracker.core.errors import UnknownConnectorError
from jobtracker.mail.generic.imap import MailImapClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_calendar import GOOGLE_REQUEST, cancel_of, moved_invite  # noqa: E402

ROOT_URL = "https://dav.example.com/"
CAL_URL = "https://dav.example.com/123/calendars/interviews/"

MULTISTATUS = '<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">{}</d:multistatus>'


def _response(href: str, props: str) -> str:
    return (
        f"<d:response><d:href>{href}</d:href><d:propstat><d:prop>{props}</d:prop></d:propstat></d:response>"
    )


class FakeServer:
    """A tiny CalDAV server that, like some hosted servers, rejects UID prop-filters with 412."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[str, str]] = {}
        self.requests: list[tuple[str, str]] = []
        self.n = 0

    def __call__(self, request: urllib.request.Request, timeout: float):
        method, url = request.get_method(), request.full_url
        body = (request.data or b"").decode()
        headers = {k.lower(): v for k, v in request.header_items()}
        self.requests.append((method, url))
        assert headers["authorization"].startswith("Basic ")
        if method == "PROPFIND" and url == ROOT_URL:
            props = "<d:current-user-principal><d:href>/123/principal/</d:href></d:current-user-principal>"
            return 207, MULTISTATUS.format(_response("/", props)), {}
        if method == "PROPFIND" and url.endswith("/principal/"):
            props = "<c:calendar-home-set><d:href>/123/calendars/</d:href></c:calendar-home-set>"
            return 207, MULTISTATUS.format(_response("/123/principal/", props)), {}
        if method == "PROPFIND" and url.endswith("/calendars/"):
            items = [
                _response("/123/calendars/", "<d:resourcetype><d:collection/></d:resourcetype>"),
                _response(
                    "/123/calendars/interviews/",
                    "<d:displayname>Interviews</d:displayname>"
                    "<d:resourcetype><d:collection/><c:calendar/></d:resourcetype>",
                ),
            ]
            return 207, MULTISTATUS.format("".join(items)), {}
        if method == "REPORT":
            if "prop-filter" in body:
                return 412, "precondition failed", {}
            items = "".join(
                _response(
                    href.replace("https://dav.example.com", ""),
                    f"<d:getetag>{etag}</d:getetag><c:calendar-data>{data.replace('&', '&amp;')}</c:calendar-data>",
                )
                for href, (etag, data) in self.objects.items()
            )
            return 207, MULTISTATUS.format(items), {}
        if method == "GET":
            if url in self.objects:
                etag, data = self.objects[url]
                return 200, data, {"ETag": etag}
            return 404, "", {}
        if method == "PUT":
            if headers.get("if-none-match") == "*" and url in self.objects:
                return 412, "exists", {}
            if "if-match" in headers and self.objects.get(url, ("",))[0] != headers["if-match"]:
                return 412, "changed", {}
            self.n += 1
            created = url not in self.objects
            self.objects[url] = (f'"{self.n}"', body)
            return (201 if created else 204), "", {}
        if method == "DELETE":
            self.objects.pop(url, None)
            return 204, "", {}
        return 400, "unexpected", {}


class CalDAVTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = FakeServer()
        self.backend = CalDAVBackend(ROOT_URL, "user", "secret", transport=self.server)

    def test_discovery_and_protocol(self) -> None:
        self.assertIsInstance(self.backend, CalendarBackend)
        self.assertEqual(calendar_url(self.backend, "Interviews"), CAL_URL)
        with self.assertRaisesRegex(ValueError, "Available: Interviews"):
            calendar_url(self.backend, "Missing")
        self.assertEqual(self.backend.health(), [])
        self.assertEqual(self.backend.object_url(CAL_URL, "a b@c"), CAL_URL + "a_b_c.ics")

    def test_crud_and_uid_lookup_without_prop_filter(self) -> None:
        url = self.backend.object_url(CAL_URL, "abc123@calendar.example")
        self.assertEqual(self.backend.put(url, GOOGLE_REQUEST, None), 201)
        with self.assertRaisesRegex(RuntimeError, "PUT returned 412"):
            self.backend.put(url, GOOGLE_REQUEST, None)
        hits = find_by_uid(self.backend, CAL_URL, "abc123@calendar.example")
        self.assertEqual([hit.url for hit in hits], [url])
        foreign = CAL_URL + "foreign.ics"
        self.server.objects[foreign] = ('"x"', GOOGLE_REQUEST.replace("abc123", "other"))
        around = datetime(2030, 12, 1, 14, tzinfo=timezone.utc)
        hits = find_by_uid(self.backend, CAL_URL, "other@calendar.example", around)
        self.assertEqual([hit.url for hit in hits], [foreign])
        self.assertEqual(find_by_uid(self.backend, CAL_URL, "none@calendar.example"), [])
        self.assertTrue(any(method == "REPORT" for method, _ in self.server.requests))
        etag = self.backend.get(url).etag
        self.backend.delete(url, etag)
        self.assertIsNone(self.backend.get(url))

    def test_errors_and_health(self) -> None:
        failing = CalDAVBackend(ROOT_URL, "user", "pw", transport=lambda request, timeout: (401, "", {}))
        self.assertIn("login or discovery failed", failing.health()[0])
        with self.assertRaisesRegex(RuntimeError, "REPORT returned 401"):
            failing.all_events(CAL_URL)
        with self.assertRaisesRegex(RuntimeError, "DELETE returned 401"):
            failing.delete(CAL_URL + "x.ics", None)
        self.assertEqual(CalDAVBackend(ROOT_URL, "", "", transport=self.server).health()[0][:6], "CalDAV")
        fixed = CalDAVBackend("", "u", "p", calendar_url=CAL_URL, transport=self.server)
        self.assertEqual(fixed.health(), [])
        with self.assertRaises(ValueError):
            CalDAVBackend("", "u", "p")

    def test_factory_reads_credentials_from_env_names(self) -> None:
        options = {"url": ROOT_URL, "user_env": "CAL_U", "password_env": "CAL_P", "timeout_seconds": 5}
        backend = build_caldav_backend(options, {"CAL_U": "u", "CAL_P": "p"})
        self.assertEqual(backend.timeout, 5.0)
        self.assertEqual(backend._auth, "Basic dTpw")
        missing = build_caldav_backend({"url": ROOT_URL}, {})
        self.assertEqual(missing.health(), ["CalDAV user name or password is not set in the environment"])


class IcsDirectoryTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            backend = IcsDirectoryBackend(Path(temp) / "cal")
            self.assertEqual(backend.calendars(), [])
            self.assertEqual(backend.health(), [])
            self.assertTrue(IcsDirectoryBackend(Path(temp) / "x.ics").health() == [])
            cal = calendar_url(backend, "Interviews")
            self.assertEqual(backend.health(), [])
            self.assertEqual([c.name for c in backend.calendars()], ["Interviews"])
            url = backend.object_url(cal, "abc@x")
            self.assertEqual(backend.put(url, GOOGLE_REQUEST, None), 201)
            with self.assertRaises(RuntimeError):
                backend.put(url, GOOGLE_REQUEST, None)
            with self.assertRaises(RuntimeError):
                backend.put(url, GOOGLE_REQUEST, '"stale"')
            etag = backend.get(url).etag
            self.assertEqual(backend.put(url, GOOGLE_REQUEST, etag), 204)
            inside = backend.by_range(
                cal, datetime(2030, 12, 1, tzinfo=timezone.utc), datetime(2030, 12, 2, tzinfo=timezone.utc)
            )
            outside = backend.by_range(
                cal, datetime(2031, 1, 1, tzinfo=timezone.utc), datetime(2031, 2, 1, tzinfo=timezone.utc)
            )
            self.assertEqual((len(inside), len(outside)), (1, 0))
            with self.assertRaises(RuntimeError):
                backend.delete(url, '"stale"')
            backend.delete(url, None)
            with self.assertRaises(RuntimeError):
                backend.delete(url, None)
            for bad in ("", "..", "a/b"):
                with self.assertRaises(ValueError):
                    backend.calendar_url(bad)


class RegistryAndConfigTests(unittest.TestCase):
    def test_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backend = build_calendar_backend({"kind": "icsdir", "path": "outputs/cal"}, root=root)
            self.assertEqual(backend.path, root / "outputs/cal")
            caldav = build_calendar_backend({"url": ROOT_URL}, root=root, env={})
            self.assertEqual(caldav.slug, "caldav")
            with self.assertRaises(UnknownConnectorError):
                build_calendar_backend({"kind": "nope"}, root=root)

    def _config(self, temp: str, calendar: str) -> Path:
        path = Path(temp) / "config/jobsearch.toml"
        path.parent.mkdir(parents=True)
        path.write_text(
            'schema_version = 1\n[store]\nbackend = "sqlite"\n'
            '[pipelines.p]\ntype = "jobboard"\nprofile = "generic"\nproviders = ["x"]\n' + calendar,
            encoding="utf-8",
        )
        return path

    def test_config_section(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self._config(
                temp, '[calendar]\nkind = "CalDAV"\nurl = "https://dav.example.com/"\nalarms_minutes = [10]\n'
            )
            config = load_app_config(root=temp)
            self.assertEqual(config.calendar["kind"], "caldav")
        for bad in ('password = "x"', "alarms_minutes = [-1]", 'calendar = ""', "kind = 3"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as temp:
                self._config(temp, f"[calendar]\n{bad}\n")
                with self.assertRaises(ConfigValidationError):
                    load_app_config(root=temp)


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        config = self.root / "config/jobsearch.toml"
        config.parent.mkdir(parents=True)
        config.write_text(
            'schema_version = 1\n[store]\nbackend = "sqlite"\n'
            '[pipelines.p]\ntype = "jobboard"\nprofile = "generic"\nproviders = ["x"]\n'
            '[calendar]\nkind = "icsdir"\npath = "outputs/calendar"\ncalendar = "Interviews"\n'
            'default_timezone = "Europe/Madrid"\n',
            encoding="utf-8",
        )
        (self.root / "invite.ics").write_text(GOOGLE_REQUEST, encoding="utf-8")
        (self.root / "moved.ics").write_text(moved_invite(), encoding="utf-8")
        (self.root / "cancel.ics").write_text(cancel_of(moved_invite(), seq=3), encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {"JOBTRACKER_CALENDAR_SELF_EMAILS": "candidate@example.com"})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.temp.cleanup()

    def run_cli(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["calendar", *argv[:1], "--root", str(self.root), *argv[1:]])
        return code, out.getvalue()

    def test_end_to_end(self) -> None:
        code, out = self.run_cli("parse", "--ics", "invite.ics", "--out", "outputs/spec.json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["specs"][0]["key"], "invite:abc123@calendar.example")
        code, out = self.run_cli("apply", "outputs/spec.json", "--dry-run")
        self.assertEqual(json.loads(out)[0]["result"], "would_create")
        code, out = self.run_cli("apply", "outputs/spec.json")
        self.assertEqual(json.loads(out)[0]["result"], "created")
        code, out = self.run_cli("apply", "--ics", "moved.ics", "--evidence", "imap://Jobs/2")
        self.assertEqual(json.loads(out)[0]["result"], "updated")
        code, out = self.run_cli("calendars")
        self.assertEqual(json.loads(out)[0]["name"], "Interviews")
        code, out = self.run_cli("list", "--from", "2030-11-01", "--to", "2031-01-01")
        self.assertIn("M  CONF  Interview with Acme", out)
        code, out = self.run_cli(
            "list", "--from", "2030-11-01", "--to", "2031-01-01", "--json", "--managed-only"
        )
        self.assertEqual(json.loads(out)[0]["start_local"], "2030-12-01T17:00+01:00")
        key = "invite:abc123@calendar.example"
        code, out = self.run_cli("update", "--key", key, "--start", "2030-12-02T09:00", "--evidence", "e")
        self.assertEqual(json.loads(out)["result"], "updated")
        code, out = self.run_cli("export", "--key", key)
        self.assertEqual(json.loads(out)["end"], "2030-12-02T09:45:00+01:00")
        code, out = self.run_cli("export", "--key", key, "--format", "ics")
        self.assertIn("X-JOBSEARCH-KEY:invite:abc123@calendar.example", out)
        code, out = self.run_cli("cancel", "--key", key, "--reason", "moved", "--evidence", "e")
        self.assertEqual(json.loads(out)["result"], "cancelled")
        code, _ = self.run_cli("delete", "--key", key)
        self.assertEqual(code, 2)
        code, out = self.run_cli("delete", "--key", key, "--yes")
        self.assertEqual(json.loads(out)["result"], "deleted")
        code, out = self.run_cli("export", "--key", key)
        self.assertEqual((code, json.loads(out)["result"]), (1, "not_found"))
        code, out = self.run_cli("update", "--uid", "missing")
        self.assertEqual(code, 1)
        code, out = self.run_cli("cancel", "--uid", "missing", "--reason", "r", "--evidence", "e")
        self.assertEqual(code, 1)
        (self.root / "bad.json").write_text('{"action": "upsert", "key": "k"}', encoding="utf-8")
        code, out = self.run_cli("apply", "bad.json")
        self.assertEqual((code, json.loads(out)[0]["result"]), (1, "invalid"))
        self.assertEqual(self.run_cli("apply")[0], 2)
        self.assertEqual(self.run_cli("export")[0], 2)

    def test_parse_eml_and_reply(self) -> None:
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["Subject"], msg["From"] = "Interview reminder", "hr@corp.example"
        msg.set_content("See you tomorrow")
        (self.root / "m.eml").write_bytes(msg.as_bytes())
        code, out = self.run_cli("parse", "--eml", "m.eml")
        self.assertEqual(json.loads(out)["suggested_action"], "verify_existing")
        code, out = self.run_cli("reply", "--ics", "invite.ics", "--partstat", "DECLINED")
        self.assertIn("METHOD:REPLY", out)
        code, out = self.run_cli("reply", "--ics", "invite.ics", "--partstat", "ACCEPTED", "--out", "r.ics")
        self.assertEqual(json.loads(out)["to"], "recruiter@acme.example")
        self.assertTrue((self.root / "r.ics").exists())
        code, _ = self.run_cli("reply", "--ics", "invite.ics", "--partstat", "ACCEPTED", "--send")
        self.assertEqual(code, 2)
        with mock.patch.object(cli, "send_reply", return_value={"result": "sent"}) as sender:
            code, out = self.run_cli(
                "reply", "--ics", "invite.ics", "--partstat", "ACCEPTED", "--send", "--confirm-send"
            )
        self.assertEqual((code, json.loads(out)["result"]), (0, "sent"))
        self.assertEqual(sender.call_args.args[1], "recruiter@acme.example")

    def test_parse_imap_uses_read_only_fetch(self) -> None:
        with (
            mock.patch.object(MailImapClient, "__init__", return_value=None),
            mock.patch.object(MailImapClient, "__enter__", lambda self: self),
            mock.patch.object(MailImapClient, "__exit__", return_value=None),
            mock.patch.object(
                MailImapClient, "fetch_raw", return_value=b"Subject: Interview cancelled\n\nSorry."
            ),
        ):
            code, out = self.run_cli("parse", "--imap", "Jobs:42")
        result = json.loads(out)
        self.assertEqual(
            (result["evidence"], result["suggested_action"]), ("imap://Jobs/42", "cancel_existing")
        )
        self.assertEqual(self.run_cli("parse", "--imap", "no-uid")[0], 2)

    def test_unconfigured_calendar(self) -> None:
        (self.root / "config/jobsearch.toml").write_text(
            'schema_version = 1\n[store]\nbackend = "sqlite"\n'
            '[pipelines.p]\ntype = "jobboard"\nprofile = "generic"\nproviders = ["x"]\n',
            encoding="utf-8",
        )
        self.assertEqual(self.run_cli("list")[0], 2)
        self.assertEqual(self.run_cli("calendars")[0], 2)


class DoctorTests(unittest.TestCase):
    def test_doctor_reports_calendar_problems(self) -> None:
        from jobtracker.automation import check_calendar_config

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "file").write_text("x", encoding="utf-8")
            config = mock.Mock(root=root, calendar={"kind": "icsdir", "path": "file"})
            self.assertEqual(check_calendar_config(config, skip_network=True), [])
            self.assertIn("not a directory", check_calendar_config(config)[0])
            config.calendar = {"kind": "icsdir", "default_timezone": "Mars/Base"}
            self.assertIn("Mars/Base", check_calendar_config(config, skip_network=True)[0])
            config.calendar = {"kind": "nope"}
            self.assertIn("Unknown calendar backend", check_calendar_config(config, skip_network=True)[0])


class FetchRawTests(unittest.TestCase):
    def test_fetch_raw_selects_read_only(self) -> None:
        client = MailImapClient.__new__(MailImapClient)
        conn = mock.Mock()
        conn.select.return_value = ("OK", [b"1"])
        conn.uid.return_value = ("OK", [(b"1 (BODY[] {3}", b"raw")])
        client._conn = conn
        self.assertEqual(client.fetch_raw("Jobs", "7"), b"raw")
        conn.select.assert_called_once_with('"Jobs"', readonly=True)
        conn.select.return_value = ("NO", [])
        with self.assertRaises(RuntimeError):
            client.fetch_raw("Missing", "1")


class ReplySendTests(unittest.TestCase):
    def test_send_uses_starttls_and_requires_credentials(self) -> None:
        smtp = mock.MagicMock()
        smtp.__enter__.return_value = smtp
        env = {
            "JOBTRACKER_SMTP_HOST": "smtp.example.com",
            "JOBTRACKER_SMTP_USER": "u",
            "JOBTRACKER_SMTP_PASSWORD": "p",
        }
        result = send_reply(
            "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
            "recruiter@acme.example",
            "Accepted: Interview",
            "candidate@example.com",
            outbox={"port": 587},
            env=env,
            smtp_factory=lambda host, port: smtp,
        )
        self.assertEqual(result["result"], "sent")
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("u", "p")
        sent = smtp.send_message.call_args.args[0]
        self.assertEqual(sent["From"], "candidate@example.com")
        self.assertIn("text/calendar", sent.as_string())
        with self.assertRaises(RuntimeError):
            send_reply("x", "a@example.com", "s", "b@example.com", outbox={}, env={})


if __name__ == "__main__":
    unittest.main()
