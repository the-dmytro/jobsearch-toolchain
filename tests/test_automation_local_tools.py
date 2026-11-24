from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest import mock

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

from jobtracker import cli as jobtracker_cli
from jobtracker.automation_state import AutomationStateStore
from jobtracker.dedupe import LocalDedupeIndex, apply_db_dedupe_matches, dedupe_payload
from jobtracker.gmail_imap import (
    MailImapClient,
    filter_provider_messages,
    parse_email_message,
    resolve_mail_folder,
)
from jobtracker.upwork_email import parse_upwork_alert_payload
from jobtracker.validation import normalize_provider_external_id, validate_payload


class AutomationLocalToolsTests(unittest.TestCase):
    def test_validate_payload_normalizes_upwork_external_ids(self) -> None:
        payload = {
            "run": {
                "run_key": "upwork-2026-05-12-0958",
                "status": "completed",
                "report_email_sent": True,
            },
            "source_items": [
                {
                    "source_type": "email",
                    "external_id": "gmail-msg-1",
                    "subject": "Upwork alert",
                }
            ],
            "opportunities": [
                {
                    "external_id": "~022047650000881711706",
                    "title": "Build a SwiftUI prototype",
                    "company": "Verified client",
                    "source_url": "https://www.upwork.com/jobs/~022047650000881711706/",
                    "source_items": ["gmail-msg-1"],
                    "evaluation": {"verdict": "Apply", "confidence": "High"},
                }
            ],
        }

        result = validate_payload(payload, provider="upwork")

        self.assertFalse(result.errors)
        self.assertEqual(result.normalized["opportunities"][0]["external_id"], "022047650000881711706")

    def test_validate_payload_reports_missing_required_opportunity_fields(self) -> None:
        payload = {
            "run": {"run_key": "linkedin-2026-05-12", "status": "completed"},
            "opportunities": [{"company": "Acme"}],
        }

        result = validate_payload(payload, provider="linkedin")

        self.assertIn("opportunities[0].title is required", result.errors)
        self.assertIn("opportunities[0] needs external_id or source_url", result.errors)

    def test_legacy_aliases_are_read_into_canonical_fields_with_warnings(self) -> None:
        payload = {
            "run": {"run_key": "legacy-1", "status": "completed"},
            "emails": [{"source_type": "email", "external_id": "message-1"}],
            "jobs": [{"title": "Software Engineer", "external_id": "job-1"}],
        }

        result = validate_payload(payload, provider="example")

        self.assertEqual(result.normalized["source_items"], payload["emails"])
        self.assertEqual(result.normalized["opportunities"], payload["jobs"])
        self.assertTrue(any("emails" in warning for warning in result.warnings))
        self.assertTrue(any("jobs" in warning for warning in result.warnings))

    def test_normalize_provider_external_id_extracts_ids_from_urls(self) -> None:
        self.assertEqual(
            normalize_provider_external_id("upwork", "https://www.upwork.com/jobs/~022047650000881711706/"),
            "022047650000881711706",
        )
        self.assertEqual(
            normalize_provider_external_id(
                "linkedin", "https://www.linkedin.com/jobs/view/4242424242/?trackingId=x"
            ),
            "4242424242",
        )

    def test_state_store_tracks_pending_stages_and_email_idempotency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AutomationStateStore(Path(temp_dir) / "state.sqlite")
            upserted = store.upsert_source_items(
                "upwork",
                [
                    {
                        "source_type": "email",
                        "external_id": "gmail-msg-1",
                        "subject": "Upwork alert",
                        "timestamp": "2026-05-12T09:58:00+00:00",
                        "raw_text": "body",
                    }
                ],
            )

            self.assertEqual(upserted["upserted"], 1)
            self.assertEqual(
                [item["external_id"] for item in store.pending_source_items("upwork", "evaluation")],
                ["gmail-msg-1"],
            )

            store.mark_source_stage("upwork", "email", "gmail-msg-1", "evaluated")

            self.assertEqual(store.pending_source_items("upwork", "evaluation"), [])
            self.assertTrue(
                store.reserve_email(
                    "email-key-1",
                    provider="upwork",
                    run_key="upwork-1",
                    to_address="job@example.com",
                    subject="Report",
                )
            )
            store.mark_email_sent("email-key-1")
            self.assertFalse(
                store.reserve_email(
                    "email-key-1",
                    provider="upwork",
                    run_key="upwork-1",
                    to_address="job@example.com",
                    subject="Report",
                )
            )

    def test_parse_email_message_extracts_body_and_links(self) -> None:
        message = EmailMessage()
        message["Subject"] = "Upwork: SwiftUI prototype"
        message["Message-ID"] = "<gmail-msg-1@example.com>"
        message["Date"] = "Tue, 12 May 2026 09:58:00 +0000"
        message.set_content("Plain fallback https://example.com/plain")
        message.add_alternative(
            '<html><body><a href="https://www.upwork.com/jobs/~022047650000881711706/">View job</a></body></html>',
            subtype="html",
        )

        parsed = parse_email_message(message.as_bytes())

        self.assertEqual(parsed["message_id"], "gmail-msg-1@example.com")
        self.assertEqual(parsed["subject"], "Upwork: SwiftUI prototype")
        self.assertIn("Plain fallback", parsed["text"])
        self.assertIn("https://www.upwork.com/jobs/~022047650000881711706/", parsed["links"])

    def test_parse_upwork_alert_payload_extracts_job_cards_deterministically(self) -> None:
        payload = {
            "run": {"run_key": "upwork-mail-fetch-20260518081127"},
            "source_items": [
                {
                    "source_type": "email",
                    "external_id": "upwork-email-1",
                    "subject": "New job alert: Finish Job-Search App for Québec",
                    "timestamp": "2026-05-15T02:22:47+00:00",
                    "text": (
                        "New job alert Hi Candidate, This job was just posted and matches your alert settings. "
                        "---------- Finish Job-Search App for Québec: "
                        "https://www.upwork.com/jobs/~022055111032577149695?link=title&n=null "
                        "Hourly: $15.00 - $40.00 · Est. time: 1 to 3 months · Posted Fri, May 15 "
                        "I'm looking for a team or developer to finish a small, well-scoped job-search app. "
                        "more: https://www.upwork.com/jobs/~022055111032577149695?link=more&n=null "
                        "Skills: iPad App Development: https://www.upwork.com/s/emails/nx/search/jobs/?x=1 "
                        "Payment verified · 4.88 stars · $23K spent · Canada "
                        "---------- View job details: https://www.upwork.com/jobs/~022055111032577149695?frkscc=abc"
                    ),
                }
            ],
        }

        parsed = parse_upwork_alert_payload(
            payload, run_key="upwork-2026-05-18-0811", now="2026-05-18T08:11:27+00:00"
        )

        self.assertEqual(parsed["run"]["run_key"], "upwork-2026-05-18-0811")
        self.assertEqual(parsed["run"]["opportunities_count"], 1)
        opportunity = parsed["opportunities"][0]
        self.assertEqual(opportunity["external_id"], "022055111032577149695")
        self.assertEqual(opportunity["title"], "Finish Job-Search App for Québec")
        self.assertEqual(opportunity["source_url"], "https://www.upwork.com/jobs/~022055111032577149695/")
        self.assertEqual(opportunity["engagement_type"], "hourly")
        self.assertEqual(opportunity["compensation_text"], "Hourly: $15.00 - $40.00")
        self.assertEqual(opportunity["metadata"]["estimated_time"], "1 to 3 months")
        self.assertEqual(
            opportunity["metadata"]["client_economics"], "Payment verified · 4.88 stars · $23K spent · Canada"
        )
        self.assertEqual(opportunity["metadata"]["page_enrichment_status"], "skipped_cloudflare_by_design")
        self.assertEqual(opportunity["metadata"]["skills"], ["iPad App Development"])

    def test_fetch_label_messages_reads_icloud_body_peek_literals(self) -> None:
        message = EmailMessage()
        message["Subject"] = "New job: SwiftUI prototype"
        message["Message-ID"] = "<icloud-msg-1@example.com>"
        message["Date"] = "Tue, 12 May 2026 09:58:00 +0000"
        message.set_content("A new Upwork job matches your saved search.")

        class FakeImapConnection:
            def __init__(self) -> None:
                self.fetch_specs: list[str] = []

            def select(self, label: str, readonly: bool = True):
                return "OK", [b"1"]

            def uid(self, command: str, _charset, *criteria):
                if command == "search":
                    return "OK", [b"42"]
                fetch_spec = criteria[0]
                self.fetch_specs.append(fetch_spec)
                if fetch_spec == "(BODY.PEEK[])":
                    return "OK", [(b"42 (UID 42 BODY[] {123}", message.as_bytes()), b")"]
                return "OK", [b"42 (UID 42)"]

        connection = FakeImapConnection()
        client = MailImapClient(host="imap.example.com", user="user", password="password")
        client._conn = connection

        messages = client.fetch_label_messages("Upwork", limit=1)

        self.assertEqual(connection.fetch_specs, ["(BODY.PEEK[])"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["external_id"], "icloud-msg-1@example.com")
        self.assertEqual(messages[0]["imap_uid"], "42")

    def test_resolve_mail_folder_accepts_icloud_job_subfolders(self) -> None:
        folders = ["Archive", "Job", "job/LinkedIn", "Upwork", "job/Upwork"]

        self.assertEqual(resolve_mail_folder(folders, "linkedin"), "job/LinkedIn")
        self.assertEqual(resolve_mail_folder(folders, "upwork"), "Upwork")
        self.assertEqual(resolve_mail_folder(folders, "job-responses"), "Job")

    def test_discover_mail_folders_resolves_from_listed_folders_before_close(self) -> None:
        class FakeMailClient:
            def __init__(self) -> None:
                self.closed = False

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                self.closed = True

            def list_folders(self) -> list[str]:
                if self.closed:
                    raise RuntimeError("connection closed")
                return ["Archive", "Job", "Job/LinkedIn", "Upwork"]

            def resolve_folder(self, provider: str, explicit_folder: str | None = None) -> str:
                if self.closed:
                    raise RuntimeError("connection closed")
                return resolve_mail_folder(self.list_folders(), provider, explicit_folder=explicit_folder)

        buffer = io.StringIO()
        with mock.patch.object(jobtracker_cli, "MailImapClient", return_value=FakeMailClient()):
            with contextlib.redirect_stdout(buffer):
                exit_code = jobtracker_cli.cmd_discover_mail_folders(argparse.Namespace())

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload["resolved"], {"upwork": "Upwork", "linkedin": "Job/LinkedIn", "job-responses": "Job"}
        )

    def test_filter_provider_messages_keeps_only_alert_like_messages(self) -> None:
        messages = [
            {
                "external_id": "linkedin-alert",
                "from": "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
                "subject": "New jobs similar to Senior iOS Engineer",
                "text": "See jobs matching your alert.",
                "links": ["https://www.linkedin.com/jobs/view/4242424242/"],
            },
            {
                "external_id": "linkedin-fit",
                "from": "LinkedIn Jobs <jobs-listings@linkedin.com>",
                "subject": "You may be a fit for Qonto's Senior Product Engineer - iOS/Swift role",
                "text": "View this LinkedIn job recommendation.",
                "links": ["https://www.linkedin.com/jobs/view/4242424243/"],
            },
            {
                "external_id": "linkedin-application-sent",
                "from": "LinkedIn Jobs <jobs-noreply@linkedin.com>",
                "subject": "Candidate, your application was sent to Example Company",
                "text": "View your application for this LinkedIn job.",
                "links": ["https://www.linkedin.com/jobs/view/4407831006/"],
            },
            {
                "external_id": "linkedin-application-received",
                "from": "Jobgether <no-reply@match.jobgether.com>",
                "subject": "Application received: Desarrollador iOS Senior - View your match score",
                "text": "Your application has been received.",
                "links": ["https://jobgether.com/applicant"],
            },
            {
                "external_id": "linkedin-message-summary",
                "from": "LinkedIn <messages-noreply@linkedin.com>",
                "subject": "job openings in the past week",
                "text": "A company posted an update.",
                "links": ["https://www.linkedin.com/feed/"],
            },
            {
                "external_id": "linkedin-security",
                "from": "LinkedIn <security-noreply@linkedin.com>",
                "subject": "Your LinkedIn verification code",
                "text": "Use this code to sign in.",
                "links": [],
            },
            {
                "external_id": "upwork-alert",
                "from": "Upwork <noreply@upwork.com>",
                "subject": "New job: SwiftUI prototype",
                "text": "A new job matches your saved search.",
                "links": ["https://www.upwork.com/jobs/~022047650000881711706/"],
            },
            {
                "external_id": "report",
                "from": "Automation <job@example.com>",
                "subject": "Upwork job alerts - report",
                "text": "Automation summary",
                "links": [],
            },
            {
                "external_id": "gmail-sent-report",
                "from": "Me <person@example.com>",
                "subject": "Upwork job alerts - 2026-05-18 09:00 - no good matches",
                "text": "Upwork jobs worth attention: none",
                "links": ["https://www.upwork.com/jobs/~022047650000881711706/"],
            },
        ]

        with mock.patch.dict("os.environ", {"JOBTRACKER_OWN_SENDERS": "job@example.com"}, clear=False):
            linkedin = filter_provider_messages("linkedin", messages)
            upwork = filter_provider_messages("upwork", messages)

        self.assertEqual(
            [item["external_id"] for item in linkedin.matched], ["linkedin-alert", "linkedin-fit"]
        )
        self.assertEqual([item["external_id"] for item in upwork.matched], ["upwork-alert"])
        self.assertEqual(linkedin.skipped, 7)
        self.assertEqual(upwork.skipped, 8)

    def test_mail_imap_client_prefers_generic_env_but_keeps_gmail_fallback(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "JOBTRACKER_IMAP_HOST": "imap.mail.me.com",
                "JOBTRACKER_IMAP_USER": "icloud@example.com",
                "JOBTRACKER_IMAP_PASSWORD": "icloud-app-password",
                "GMAIL_IMAP_HOST": "imap.gmail.com",
                "GMAIL_IMAP_USER": "gmail@example.com",
                "GMAIL_IMAP_PASSWORD": "gmail-app-password",
            },
            clear=True,
        ):
            client = MailImapClient()

        self.assertEqual(client.host, "imap.mail.me.com")
        self.assertEqual(client.user, "icloud@example.com")
        self.assertEqual(client.password, "icloud-app-password")

        current_dir = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                with mock.patch.dict(
                    "os.environ",
                    {
                        "GMAIL_IMAP_HOST": "imap.gmail.com",
                        "GMAIL_IMAP_USER": "gmail@example.com",
                        "GMAIL_IMAP_PASSWORD": "gmail-app-password",
                    },
                    clear=True,
                ):
                    fallback = MailImapClient()
            finally:
                os.chdir(current_dir)

        self.assertEqual(fallback.host, "imap.gmail.com")
        self.assertEqual(fallback.user, "gmail@example.com")

    def test_mail_imap_client_loads_dotenv_file(self) -> None:
        current_dir = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text(
                "\n".join(
                    [
                        "JOBTRACKER_IMAP_HOST=imap.mail.me.com",
                        "JOBTRACKER_IMAP_USER=icloud@example.com",
                        "JOBTRACKER_IMAP_PASSWORD=icloud-app-password",
                    ]
                ),
                encoding="utf-8",
            )
            try:
                os.chdir(root)
                with mock.patch.dict("os.environ", {}, clear=True):
                    client = MailImapClient()
            finally:
                os.chdir(current_dir)

        self.assertEqual(client.host, "imap.mail.me.com")
        self.assertEqual(client.user, "icloud@example.com")
        self.assertEqual(client.password, "icloud-app-password")

    def test_local_dedupe_suppresses_exact_and_recent_application_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            prior = {
                "run": {
                    "run_key": "upwork-2026-05-10",
                    "finished_at": "2026-05-10T10:00:00+00:00",
                    "report_email_sent": True,
                },
                "opportunities": [
                    {
                        "external_id": "022047650000881711706",
                        "company": "Acme Apps",
                        "title": "Senior iOS Engineer",
                        "application": {"status": "applied", "applied_at": "2026-05-10"},
                    }
                ],
            }
            candidate = {
                "run": {"run_key": "upwork-2026-05-12"},
                "opportunities": [
                    {
                        "external_id": "~022047650000881711706",
                        "company": "Acme Apps",
                        "title": "Senior iOS Engineer",
                    },
                    {
                        "external_id": "new-1",
                        "company": "Acme Apps",
                        "title": "iOS Developer",
                    },
                ],
            }
            (root / "prior.payload.json").write_text(json.dumps(prior), encoding="utf-8")

            index = LocalDedupeIndex.from_payload_dir(root, now="2026-05-12T12:00:00+00:00")
            enriched = dedupe_payload(candidate, provider="upwork", index=index)

            first, second = enriched["opportunities"]
            self.assertEqual(first["dedupe_status"], "exact_external_id")
            self.assertEqual(first["email_policy"], "suppress_detail")
            self.assertIn("exact_external_id", first["dedupe_reasons"])
            self.assertEqual(second["dedupe_status"], "same_company_recent_application")
            self.assertEqual(second["email_policy"], "suppress_detail")

    def test_local_dedupe_can_exclude_current_payload_from_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_path = root / "current.payload.json"
            candidate = {
                "run": {"run_key": "upwork-2026-05-12"},
                "opportunities": [
                    {
                        "external_id": "~022047650000881711706",
                        "company": "Acme Apps",
                        "title": "Senior iOS Engineer",
                    }
                ],
            }
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

            index = LocalDedupeIndex.from_payload_dir(root, exclude_paths=[candidate_path])
            enriched = dedupe_payload(candidate, provider="upwork", index=index)

            self.assertEqual(enriched["opportunities"][0]["dedupe_status"], "new")
            self.assertEqual(enriched["opportunities"][0]["email_policy"], "include_detail")

    def test_local_dedupe_can_exclude_same_run_key_sibling_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sibling = {
                "run": {"run_key": "upwork-2026-05-12"},
                "opportunities": [
                    {
                        "external_id": "~022047650000881711706",
                        "company": "Acme Apps",
                        "title": "Senior iOS Engineer",
                    }
                ],
            }
            (root / "current.normalized.payload.json").write_text(json.dumps(sibling), encoding="utf-8")
            candidate = {
                "run": {"run_key": "upwork-2026-05-12"},
                "opportunities": [
                    {
                        "external_id": "~022047650000881711706",
                        "company": "Acme Apps",
                        "title": "Senior iOS Engineer",
                    }
                ],
            }

            index = LocalDedupeIndex.from_payload_dir(root, exclude_run_keys=["upwork-2026-05-12"])
            enriched = dedupe_payload(candidate, provider="upwork", index=index)

            self.assertEqual(enriched["opportunities"][0]["dedupe_status"], "new")

    def test_db_dedupe_matches_override_local_new_status(self) -> None:
        payload = {
            "run": {"run_key": "linkedin-2026-05-18"},
            "opportunities": [
                {
                    "external_id": "4415534193",
                    "company": "Qonto",
                    "title": "Senior Product Engineer - iOS/Swift",
                    "dedupe_status": "new",
                    "email_policy": "include_detail",
                },
                {
                    "external_id": "4411502027",
                    "company": "Capitole",
                    "title": "iOS Developer",
                    "dedupe_status": "new",
                    "email_policy": "include_detail",
                },
            ],
        }

        enriched = apply_db_dedupe_matches(
            payload,
            {
                "4415534193": [
                    {
                        "match_type": "same_company_recent_application",
                        "company": "Qonto",
                        "title": "Senior iOS Engineer",
                        "application_status": "declined",
                        "applied_at": "2026-02-01",
                    }
                ]
            },
        )

        self.assertEqual(enriched["opportunities"][0]["dedupe_status"], "same_company_recent_application")
        self.assertEqual(enriched["opportunities"][0]["dedupe_source"], "db")
        self.assertEqual(enriched["opportunities"][0]["email_policy"], "suppress_detail")
        self.assertEqual(
            enriched["opportunities"][0]["dedupe_reasons"], ["db_same_company_recent_application"]
        )
        self.assertEqual(enriched["opportunities"][1]["dedupe_status"], "new")

    def test_db_dedupe_ignores_matches_only_from_current_run(self) -> None:
        payload = {
            "run": {"run_key": "upwork-2026-05-18-1616"},
            "opportunities": [
                {
                    "external_id": "022055111032577149695",
                    "company": "Current Run Co",
                    "title": "iOS bugfix",
                    "dedupe_status": "new",
                    "email_policy": "include_detail",
                },
                {
                    "external_id": "022047650000881711706",
                    "company": "Prior Run Co",
                    "title": "Senior iOS Engineer",
                    "dedupe_status": "new",
                    "email_policy": "include_detail",
                },
            ],
        }

        enriched = apply_db_dedupe_matches(
            payload,
            {
                "022055111032577149695": [
                    {
                        "match_type": "exact_external_id",
                        "company": "Current Run Co",
                        "title": "iOS bugfix",
                        "automation_run_keys": ["upwork-2026-05-18-1616"],
                    }
                ],
                "022047650000881711706": [
                    {
                        "match_type": "exact_external_id",
                        "company": "Prior Run Co",
                        "title": "Senior iOS Engineer",
                        "automation_run_keys": ["upwork-2026-05-10-0900", "upwork-2026-05-18-1616"],
                    }
                ],
            },
            exclude_run_keys=["upwork-2026-05-18-1616"],
        )

        self.assertEqual(enriched["opportunities"][0]["dedupe_status"], "new")
        self.assertEqual(enriched["opportunities"][0]["email_policy"], "include_detail")
        self.assertEqual(enriched["opportunities"][1]["dedupe_status"], "exact_external_id")
        self.assertEqual(enriched["opportunities"][1]["email_policy"], "suppress_detail")


if __name__ == "__main__":
    unittest.main()
