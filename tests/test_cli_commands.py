"""In-process tests for the ``cmd_*`` CLI handlers.

Each handler is called with an ``argparse.Namespace`` built the same way the
parser would build it, on offline or mocked paths only.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from jobtracker import cli as jobtracker_cli
from jobtracker.mail.base import SendReceipt

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "jobtracker" / "fixtures" / "provider_fetch"
TARGETS_PATH = REPO_ROOT / "jobtracker" / "fixtures" / "provider_targets.toml"
TEMPLATE_DIR = REPO_ROOT / "profile" / "templates"

# `profile/` is gitignored, so a fresh clone has no templates to seed a root from.
requires_profile_templates = unittest.skipUnless(
    TEMPLATE_DIR.exists(), "profile/templates is absent from this checkout"
)
NOW = "2026-04-29T09:00:00+00:00"

IOS_PROFILE_FILES = [
    "profile/00_INSTRUCTIONS.md",
    "profile/01_PREFERENCES.md",
    "profile/04_LINKS_AND_CONTACTS.md",
    "profile/05_ROLE_TARGETS.md",
    "profile/CV_SOURCE.md",
]


def run_command(handler, **namespace_fields) -> tuple[int, object]:
    """Call a ``cmd_*`` handler and return its exit code plus parsed stdout."""

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exit_code = handler(argparse.Namespace(**namespace_fields))
    raw = buffer.getvalue().strip()
    return exit_code, json.loads(raw) if raw.startswith(("{", "[")) else raw


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)


class ArgumentParsingTests(unittest.TestCase):
    def test_parser_wires_every_subcommand_to_a_handler(self) -> None:
        parser = jobtracker_cli.build_parser()

        for command in ("doctor", "run", "init", "validate-payload", "benchmark-sources"):
            with self.subTest(command=command):
                args = parser.parse_args(self._minimal_argv(command))
                self.assertTrue(callable(args.func))

    def _minimal_argv(self, command: str) -> list[str]:
        return {
            "doctor": ["doctor", "--skip-network"],
            "run": ["run", "jobboards", "--dry-run"],
            "init": ["init"],
            "validate-payload": ["validate-payload", "--provider", "upwork", "--payload", "x.json"],
            "benchmark-sources": ["benchmark-sources", "--providers", "dou"],
        }[command]

    def test_datetime_and_date_helpers(self) -> None:
        self.assertIsNone(jobtracker_cli._parse_datetime_arg(None))
        self.assertEqual(
            jobtracker_cli._parse_datetime_arg("2026-04-29T09:00:00Z"),
            datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
        )
        self.assertIsNone(jobtracker_cli._parse_date_arg(""))
        self.assertEqual(jobtracker_cli._parse_date_arg("2026-04-29").isoformat(), "2026-04-29")

    def test_provider_is_derived_from_the_payload_run_key(self) -> None:
        payload = {"run": {"run_key": "upwork-2026-05-12-0958"}}

        self.assertEqual(jobtracker_cli._payload_run_key(payload), "upwork-2026-05-12-0958")
        self.assertEqual(jobtracker_cli._provider_from_payload(Path("a.json"), payload, None), "upwork")
        self.assertEqual(jobtracker_cli._provider_from_payload(Path("a.json"), payload, "LinkedIn"), "linkedin")
        self.assertEqual(jobtracker_cli._provider_from_payload(Path("dou.payload.json"), {}, None), "dou")

    def test_main_maps_known_errors_to_exit_code_two(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            exit_code = jobtracker_cli.main(
                ["validate-payload", "--provider", "upwork", "--payload", str(REPO_ROOT / "nope.json")]
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("error:", buffer.getvalue())


@requires_profile_templates
class InitAndDoctorCommandTests(CliTestCase):
    def seed_project(self) -> None:
        (self.root / "config").mkdir()
        shutil.copyfile(
            REPO_ROOT / "config" / "jobsearch.example.toml",
            self.root / "config" / "jobsearch.example.toml",
        )
        shutil.copytree(REPO_ROOT / "profile" / "templates", self.root / "profile" / "templates")

    def test_cmd_init_scaffolds_the_project(self) -> None:
        self.seed_project()

        exit_code, payload = run_command(jobtracker_cli.cmd_init, root=str(self.root), force=False)

        self.assertEqual(exit_code, 0)
        self.assertIn(str(self.root / "config" / "jobsearch.toml"), payload["created"])
        self.assertTrue((self.root / "profile" / "ios.toml").exists())

    def test_cmd_doctor_returns_one_when_the_project_is_incomplete(self) -> None:
        self.seed_project()
        run_command(jobtracker_cli.cmd_init, root=str(self.root), force=False)

        exit_code, report = run_command(
            jobtracker_cli.cmd_doctor, config=None, root=str(self.root), skip_network=True
        )

        self.assertEqual(exit_code, 1)
        self.assertFalse(report["ok"])
        self.assertIn("profile_placeholders", report["checks"])

    def test_cmd_doctor_returns_zero_for_a_complete_project(self) -> None:
        self.seed_project()
        run_command(jobtracker_cli.cmd_init, root=str(self.root), force=False)
        for relative_path in IOS_PROFILE_FILES:
            path = self.root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Resolved content.\n", encoding="utf-8")

        exit_code, report = run_command(
            jobtracker_cli.cmd_doctor, config=None, root=str(self.root), skip_network=True
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(report["ok"], report["issues"])


class FetchCommandTests(CliTestCase):
    def fetch_namespace(self, **overrides) -> dict:
        fields = {
            "dry_run": True,
            "payload_out": None,
            "max_pages": 1,
            "detail_limit": 1,
            "targets": str(TARGETS_PATH),
            "fixture_dir": str(FIXTURE_DIR),
            "now": NOW,
        }
        fields.update(overrides)
        return fields

    def test_provider_fetch_commands_run_offline(self) -> None:
        handlers = {
            "dou": jobtracker_cli.cmd_fetch_dou,
            "workua": jobtracker_cli.cmd_fetch_workua,
            "djinni": jobtracker_cli.cmd_fetch_djinni,
        }
        for provider, handler in handlers.items():
            with self.subTest(provider=provider):
                payload_out = self.root / f"{provider}.payload.json"

                exit_code, summary = run_command(handler, **self.fetch_namespace(payload_out=str(payload_out)))

                self.assertEqual(exit_code, 0)
                self.assertEqual(summary["provider"], provider)
                self.assertTrue(summary["dry_run"])
                self.assertGreaterEqual(summary["opportunities"], 1)
                written = json.loads(payload_out.read_text(encoding="utf-8"))
                self.assertEqual(len(written["opportunities"]), summary["opportunities"])

    def test_greenhouse_fetch_accepts_board_tokens(self) -> None:
        exit_code, summary = run_command(
            jobtracker_cli.cmd_fetch_greenhouse_jobs,
            dry_run=True,
            payload_out=None,
            board_token=["oura"],
            max_boards=1,
            fixture_dir=str(FIXTURE_DIR),
            now=NOW,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["provider"], "greenhouse")
        self.assertEqual(summary["metrics"]["board_tokens"], ["oura"])

    def test_benchmark_sources_reports_one_result_per_provider(self) -> None:
        exit_code, payload = run_command(
            jobtracker_cli.cmd_benchmark_sources,
            providers="dou,workua,djinni,greenhouse",
            live=False,
            fixture_dir=str(FIXTURE_DIR),
            now=NOW,
            max_pages=1,
            detail_limit=1,
            max_boards=1,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "fixture")
        self.assertEqual([item["provider"] for item in payload["results"]], ["dou", "workua", "djinni", "greenhouse"])

    def test_benchmark_reports_failures_per_provider_instead_of_raising(self) -> None:
        _exit_code, payload = run_command(
            jobtracker_cli.cmd_benchmark_sources,
            providers="definitely-not-a-provider",
            live=False,
            fixture_dir=str(FIXTURE_DIR),
            now=NOW,
            max_pages=1,
            detail_limit=1,
            max_boards=1,
        )

        self.assertEqual(payload["results"][0]["status"], "partial")
        self.assertTrue(payload["results"][0]["blockers"])


class PayloadCommandTests(CliTestCase):
    def write_payload(self, name: str, payload: dict) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_validate_payload_normalizes_and_writes_the_result(self) -> None:
        payload_path = self.write_payload(
            "payload.json",
            {
                "run": {"run_key": "upwork-2026-05-12", "status": "completed"},
                "opportunities": [
                    {
                        "external_id": "~022047650000881711706",
                        "title": "Build a SwiftUI prototype",
                        "company": "Acme Apps",
                    }
                ],
            },
        )
        normalized_path = self.root / "normalized.json"

        exit_code, summary = run_command(
            jobtracker_cli.cmd_validate_payload,
            provider="upwork",
            payload=str(payload_path),
            normalized_out=str(normalized_path),
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(summary["ok"])
        normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
        self.assertEqual(normalized["opportunities"][0]["external_id"], "022047650000881711706")

    def test_validate_payload_returns_one_for_invalid_payloads(self) -> None:
        payload_path = self.write_payload(
            "bad.json",
            {"run": {"run_key": "linkedin-2026-05-12", "status": "completed"}, "opportunities": [{"company": "Acme"}]},
        )

        exit_code, summary = run_command(
            jobtracker_cli.cmd_validate_payload,
            provider="linkedin",
            payload=str(payload_path),
            normalized_out=None,
        )

        self.assertEqual(exit_code, 1)
        self.assertFalse(summary["ok"])

    def test_build_local_index_summarizes_payload_history(self) -> None:
        payload_dir = self.root / "payloads"
        self.write_payload(
            "payloads/prior.payload.json",
            {
                "run": {"run_key": "upwork-2026-05-10", "finished_at": "2026-05-10T10:00:00+00:00"},
                "opportunities": [
                    {"external_id": "022047650000881711706", "company": "Acme Apps", "title": "Senior iOS Engineer"}
                ],
            },
        )

        exit_code, payload = run_command(
            jobtracker_cli.cmd_build_local_index,
            payload_dir=str(payload_dir),
            now="2026-05-12T12:00:00+00:00",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["payload_dir"], str(payload_dir))

    def test_dedupe_candidates_enriches_without_the_database(self) -> None:
        payload_dir = self.root / "payloads"
        self.write_payload(
            "payloads/prior.payload.json",
            {
                "run": {
                    "run_key": "upwork-2026-05-10",
                    "finished_at": "2026-05-10T10:00:00+00:00",
                    "report_email_sent": True,
                },
                "opportunities": [
                    {"external_id": "022047650000881711706", "company": "Acme Apps", "title": "Senior iOS Engineer"}
                ],
            },
        )
        candidate_path = self.write_payload(
            "candidate.json",
            {
                "run": {"run_key": "upwork-2026-05-12"},
                "opportunities": [
                    {"external_id": "~022047650000881711706", "company": "Acme Apps", "title": "Senior iOS Engineer"}
                ],
            },
        )
        output_path = self.root / "enriched.json"

        exit_code, enriched = run_command(
            jobtracker_cli.cmd_dedupe_candidates,
            provider="upwork",
            payload=str(candidate_path),
            payload_dir=str(payload_dir),
            output=str(output_path),
            include_db=False,
            now="2026-05-12T12:00:00+00:00",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(enriched["opportunities"][0]["dedupe_status"], "exact_external_id")
        self.assertTrue(output_path.exists())

    def test_parse_upwork_alerts_writes_an_automation_payload(self) -> None:
        source_path = self.write_payload(
            "source.payload.json",
            {
                "source_items": [
                    {
                        "source_type": "email",
                        "external_id": "upwork-email-1",
                        "subject": "New job alert: SwiftUI checkout fix",
                        "timestamp": "2026-05-18T08:11:27+00:00",
                        "text": (
                            "---------- SwiftUI checkout fix: "
                            "https://www.upwork.com/jobs/~022056285060802688779?link=title&n=null "
                            "Hourly: $15.00 - $30.00 · Est. time: 1 to 3 months · Posted Mon, May 18 "
                            "We need help with a native iOS checkout issue. "
                            "more: https://www.upwork.com/jobs/~022056285060802688779?link=more&n=null "
                            "Skills: iOS: https://www.upwork.com/s/emails/nx/search/jobs/?x=1 "
                            "Payment verified · 5.0 stars · $4K spent · HKG"
                        ),
                    }
                ]
            },
        )
        output_path = self.root / "parsed.payload.json"

        exit_code, payload = run_command(
            jobtracker_cli.cmd_parse_upwork_alerts,
            source_payload=str(source_path),
            output=str(output_path),
            run_key="upwork-2026-05-18-0811",
            now="2026-05-18T08:11:27+00:00",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["run"]["run_key"], "upwork-2026-05-18-0811")
        self.assertEqual(payload["opportunities"][0]["external_id"], "022056285060802688779")
        self.assertTrue(output_path.exists())

    def test_sync_pending_runs_dry_run_skips_everything(self) -> None:
        payload_dir = self.root / "payloads"
        self.write_payload(
            "payloads/dou.payload.json",
            {"run": {"run_key": "dou-2026-04-29"}, "opportunities": []},
        )

        exit_code, payload = run_command(
            jobtracker_cli.cmd_sync_pending_runs,
            payload_dir=str(payload_dir),
            provider=None,
            state_db=str(self.root / "state.sqlite"),
            dry_run=True,
            keep_going=False,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["synced"], 0)
        self.assertEqual(payload["skipped"], 1)
        self.assertEqual(payload["failed"], [])

    def test_sync_pending_runs_on_an_empty_directory(self) -> None:
        (self.root / "empty").mkdir()

        exit_code, payload = run_command(
            jobtracker_cli.cmd_sync_pending_runs,
            payload_dir=str(self.root / "empty"),
            provider=None,
            state_db=str(self.root / "state.sqlite"),
            dry_run=False,
            keep_going=False,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["synced"], 0)


class MailCommandTests(CliTestCase):
    def test_send_report_email_is_idempotent(self) -> None:
        body_file = self.root / "body.txt"
        body_file.write_text("Two roles worth a look.\n", encoding="utf-8")
        state_db = self.root / "state.sqlite"
        fields = {
            "provider": "upwork",
            "run_key": "upwork-2026-05-18",
            "to": "me@example.com",
            "from_address": "robot@example.com",
            "subject": "Upwork triage",
            "body_file": str(body_file),
            "idempotency_key": None,
            "state_db": str(state_db),
        }
        sender = mock.Mock()
        sender.default_sender = "robot@example.com"
        sender.send.return_value = SendReceipt(sent=True, recipient="me@example.com", subject="Upwork triage")

        with mock.patch.object(jobtracker_cli, "SmtpMailSender", return_value=sender):
            exit_code, first = run_command(jobtracker_cli.cmd_send_report_email, **fields)
            _exit_code, second = run_command(jobtracker_cli.cmd_send_report_email, **fields)

        self.assertEqual(exit_code, 0)
        self.assertTrue(first["sent"])
        self.assertEqual(first["to"], "me@example.com")
        self.assertFalse(second["sent"])
        self.assertTrue(second["skipped"])
        sender.send.assert_called_once()

    def test_send_report_email_requires_a_recipient(self) -> None:
        body_file = self.root / "body.txt"
        body_file.write_text("body", encoding="utf-8")

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(jobtracker_cli, "load_env_file"):
                with self.assertRaises(jobtracker_cli.MissingConfigurationError):
                    run_command(
                        jobtracker_cli.cmd_send_report_email,
                        provider="upwork",
                        run_key="upwork-1",
                        to=None,
                        from_address=None,
                        subject="Report",
                        body_file=str(body_file),
                        idempotency_key=None,
                        state_db=str(self.root / "state.sqlite"),
                    )

    def test_discover_mail_folders_resolves_aliases(self) -> None:
        class FakeMailClient:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def list_folders(self) -> list[str]:
                return ["Archive", "Job", "Job/LinkedIn", "Upwork"]

        with mock.patch.object(jobtracker_cli, "MailImapClient", return_value=FakeMailClient()):
            exit_code, payload = run_command(jobtracker_cli.cmd_discover_mail_folders)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["resolved"]["upwork"], "Upwork")
        self.assertEqual(payload["resolved"]["linkedin"], "Job/LinkedIn")


class RunPipelineCommandTests(CliTestCase):
    @requires_profile_templates
    def test_cmd_run_executes_a_dry_run_pipeline(self) -> None:
        (self.root / "config").mkdir()
        shutil.copyfile(
            REPO_ROOT / "config" / "jobsearch.example.toml",
            self.root / "config" / "jobsearch.example.toml",
        )
        shutil.copytree(REPO_ROOT / "profile" / "templates", self.root / "profile" / "templates")
        run_command(jobtracker_cli.cmd_init, root=str(self.root), force=False)
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(self.root)

        exit_code, payload = run_command(
            jobtracker_cli.cmd_run,
            pipeline="jobboards",
            config=None,
            root=str(self.root),
            dry_run=True,
            fixture_dir=str(FIXTURE_DIR),
            now=NOW,
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["manifest"]["run"]["run_key"], "ua-jobboards-2026-04-29")

    def test_cmd_run_rejects_unknown_pipelines(self) -> None:
        (self.root / "config").mkdir()
        shutil.copyfile(
            REPO_ROOT / "config" / "jobsearch.example.toml",
            self.root / "config" / "jobsearch.toml",
        )

        with self.assertRaises(ValueError):
            run_command(
                jobtracker_cli.cmd_run,
                pipeline="nope",
                config=None,
                root=str(self.root),
                dry_run=True,
                fixture_dir=None,
                now=None,
            )


if __name__ == "__main__":
    unittest.main()
