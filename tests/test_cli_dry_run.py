from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliDryRunTests(unittest.TestCase):
    @property
    def fixture_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "jobtracker" / "fixtures" / "provider_fetch"

    def test_import_legacy_dry_run_outputs_summary(self) -> None:
        content = (
            "Company;Location;Kind;Domain;Vacancy link;Source;Application date;Salary requested;Stage;Decline reason;Passed;Notes\n"
            "Primer;EMEA;Remote;Payments;Link;LinkedIn;4 Feb 2025;€\\t68.000;Rejected;Other candidates;;\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as handle:
            handle.write(content)
            path = Path(handle.name)

        result = subprocess.run(
            [sys.executable, "-m", "jobtracker", "import-legacy", "--csv", str(path), "--dry-run"],
            cwd=Path(__file__).resolve().parent.parent,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["usable_rows"], 1)
        self.assertEqual(payload["providers"]["linkedin"], 1)

    def test_fetch_commands_dry_run_output_payloads(self) -> None:
        cases = [
            ("fetch-dou", ["--detail-limit", "1"]),
            ("fetch-workua", ["--detail-limit", "1"]),
            ("fetch-djinni", ["--detail-limit", "1"]),
            ("fetch-greenhouse-jobs", ["--board-token", "oura", "--max-boards", "1"]),
        ]
        for command, extra in cases:
            with self.subTest(command=command):
                with tempfile.TemporaryDirectory() as temp_dir:
                    payload_path = Path(temp_dir) / f"{command}.json"
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "jobtracker",
                            command,
                            "--dry-run",
                            "--fixture-dir",
                            str(self.fixture_dir),
                            "--now",
                            "2026-04-29T09:00:00+00:00",
                            "--payload-out",
                            str(payload_path),
                            *extra,
                        ],
                        cwd=Path(__file__).resolve().parent.parent,
                        text=True,
                        capture_output=True,
                        check=True,
                    )
                    summary = json.loads(result.stdout)
                    payload = json.loads(payload_path.read_text(encoding="utf-8"))
                    self.assertTrue(summary["dry_run"])
                    self.assertEqual(summary["opportunities"], len(payload["opportunities"]))
                    self.assertGreaterEqual(len(payload["opportunities"]), 1)

    def test_benchmark_sources_fixture_mode(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "jobtracker",
                "benchmark-sources",
                "--providers",
                "dou,workua,djinni,greenhouse",
                "--fixture-dir",
                str(self.fixture_dir),
                "--now",
                "2026-04-29T09:00:00+00:00",
                "--detail-limit",
                "1",
                "--max-boards",
                "1",
            ],
            cwd=Path(__file__).resolve().parent.parent,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "fixture")
        self.assertEqual(len(payload["results"]), 4)

    def test_prepare_jobboard_run_writes_manifest_and_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "jobtracker",
                    "prepare-jobboard-run",
                    "--profile",
                    "ios",
                    "--fixture-dir",
                    str(self.fixture_dir),
                    "--now",
                    "2026-04-29T09:00:00+00:00",
                    "--output-dir",
                    str(root),
                    "--no-db",
                ],
                cwd=Path(__file__).resolve().parent.parent,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["profile"]["slug"], "ios")
            self.assertEqual(manifest["providers"], ["dou", "workua", "djinni"])
            self.assertEqual(manifest["run"]["run_key"], "ua-jobboards-2026-04-29")
            self.assertEqual(manifest["run"]["status"], "completed")
            self.assertEqual(manifest["db"]["status"], "skipped")
            self.assertTrue(Path(manifest["manifest_path"]).exists())
            self.assertEqual(
                manifest["artifacts"]["report_path"],
                "outputs/reports/2026-04-29-ua-jobboards-triage.md",
            )
            self.assertEqual(
                manifest["artifacts"]["email_body_path"],
                str(root / "2026-04-29-ua-jobboards-email-body.txt"),
            )
            self.assertEqual(len(manifest["provider_runs"]), 3)
            for provider_run in manifest["provider_runs"]:
                self.assertEqual(provider_run["run_key"], f"{provider_run['provider']}-ua-jobboards-2026-04-29")
                self.assertGreaterEqual(provider_run["opportunities"], 1)
                self.assertTrue(Path(provider_run["payload_path"]).exists())
                self.assertTrue(Path(provider_run["normalized_payload_path"]).exists())
                self.assertTrue(Path(provider_run["deduped_payload_path"]).exists())

    def test_validate_payload_cli_writes_normalized_payload(self) -> None:
        payload = {
            "run": {"run_key": "upwork-2026-05-12", "status": "completed"},
            "opportunities": [
                {
                    "external_id": "~022047650000881711706",
                    "title": "Build a SwiftUI prototype",
                    "company": "Acme Apps",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_path = root / "payload.json"
            normalized_path = root / "normalized.json"
            payload_path.write_text(json.dumps(payload), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "jobtracker",
                    "validate-payload",
                    "--provider",
                    "upwork",
                    "--payload",
                    str(payload_path),
                    "--normalized-out",
                    str(normalized_path),
                ],
                cwd=Path(__file__).resolve().parent.parent,
                text=True,
                capture_output=True,
                check=True,
            )

            summary = json.loads(result.stdout)
            normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
            self.assertTrue(summary["ok"])
            self.assertEqual(normalized["opportunities"][0]["external_id"], "022047650000881711706")

    def test_parse_upwork_alerts_cli_writes_email_derived_payload(self) -> None:
        source_payload = {
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
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "source.payload.json"
            output_path = root / "parsed.payload.json"
            source_path.write_text(json.dumps(source_payload), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "jobtracker",
                    "parse-upwork-alerts",
                    "--source-payload",
                    str(source_path),
                    "--run-key",
                    "upwork-2026-05-18-0811",
                    "--now",
                    "2026-05-18T08:11:27+00:00",
                    "--output",
                    str(output_path),
                ],
                cwd=Path(__file__).resolve().parent.parent,
                text=True,
                capture_output=True,
                check=True,
            )

            stdout_payload = json.loads(result.stdout)
            file_payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(stdout_payload["run"]["run_key"], "upwork-2026-05-18-0811")
            self.assertEqual(file_payload["opportunities"][0]["external_id"], "022056285060802688779")
            self.assertEqual(file_payload["opportunities"][0]["metadata"]["page_enrichment_status"], "skipped_cloudflare_by_design")

    def test_dedupe_candidates_cli_enriches_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = root / "payloads"
            payload_dir.mkdir()
            (payload_dir / "prior.payload.json").write_text(
                json.dumps(
                    {
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
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            candidate_path = root / "candidate.json"
            candidate_path.write_text(
                json.dumps(
                    {
                        "run": {"run_key": "upwork-2026-05-12"},
                        "opportunities": [
                            {
                                "external_id": "~022047650000881711706",
                                "company": "Acme Apps",
                                "title": "Senior iOS Engineer",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "jobtracker",
                    "dedupe-candidates",
                    "--provider",
                    "upwork",
                    "--payload",
                    str(candidate_path),
                    "--payload-dir",
                    str(payload_dir),
                    "--now",
                    "2026-05-12T12:00:00+00:00",
                ],
                cwd=Path(__file__).resolve().parent.parent,
                text=True,
                capture_output=True,
                check=True,
            )

            enriched = json.loads(result.stdout)
            self.assertEqual(enriched["opportunities"][0]["dedupe_status"], "exact_external_id")
            self.assertEqual(enriched["opportunities"][0]["email_policy"], "suppress_detail")


if __name__ == "__main__":
    unittest.main()
