"""PostgreSQL integration tests for compact storage, shared state, documents and pruning."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

from jobtracker.automation_state import PostgresAutomationStateStore
from jobtracker.cli import main
from jobtracker.db import connect_test
from jobtracker.retention import plan_prune
from jobtracker.store.generic.postgres import PostgresJobStore
from jobtracker.store.generic.postgres_documents import list_documents, put_document, record_application
from jobtracker.testing import SKIP_REASON, prepare_test_database, test_db_reachable

TABLES = (
    "documents, opportunity_texts, email_notifications, automation_run_events, application_events, "
    "evaluations, source_items, automation_runs, artifacts, applications, opportunities, organizations, providers"
)


def payload(run_key: str, *, evaluated: bool, application: bool = False) -> dict:
    keep = {
        "external_id": "100",
        "title": "Senior iOS Engineer",
        "company": "Acme Mobile",
        "source_url": "https://jobs.example.invalid/100",
        "source_items": ["acme:100"],
        "provider_metadata": {"applicants": 12},
    }
    skip = {
        "external_id": "200",
        "title": "Data Analyst",
        "company": "Other Co",
        "source_url": "https://jobs.example.invalid/200",
        "source_items": ["acme:200"],
    }
    if evaluated:
        keep["evaluation"] = {"recommendation": "apply", "score": 8, "requirement_tags": ["swift", "uikit"]}
        skip["evaluation"] = {"recommendation": "do not apply", "score": 2}
    if application:
        keep["application"] = {"status": "applied", "applied_at": "2026-11-20", "notes": "submitted"}
    return {
        "run": {"run_key": run_key, "status": "completed"},
        "source_items": [
            {"source_type": "job_posting", "external_id": "acme:100", "raw_text": "Full iOS text " * 50},
            {"source_type": "job_posting", "external_id": "acme:200", "raw_text": "Full data text " * 50},
        ],
        "opportunities": [keep, skip],
    }


@unittest.skipUnless(test_db_reachable(), SKIP_REASON)
class PortabilityDbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        prepare_test_database()

    def setUp(self) -> None:
        with connect_test() as conn:
            with conn.cursor() as cur:
                cur.execute(f"truncate table {TABLES} restart identity cascade")
            conn.commit()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, name: str, value: dict) -> Path:
        path = self.root / "outputs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_compact_storage_text_retention_and_idempotent_application(self) -> None:
        discovered = self._write("a.deduped.payload.json", payload("acme-run-1", evaluated=False))
        evaluated = self._write(
            "a.evaluated.payload.json", payload("acme-run-1", evaluated=True, application=True)
        )
        with connect_test() as conn:
            store = PostgresJobStore(conn)
            first = store.upsert_run_payload("acme", str(discovered))
            self.assertEqual(first.stored_texts, 0)
            result = store.upsert_run_payload("acme", str(evaluated))
            self.assertEqual(result.stored_texts, 1)
            store.upsert_run_payload("acme", str(evaluated))
            with conn.cursor() as cur:
                cur.execute("select count(*) as n from source_items where raw_text is not null")
                self.assertEqual(cur.fetchone()["n"], 0)
                cur.execute("select count(*) as n from opportunity_texts")
                self.assertEqual(cur.fetchone()["n"], 1)
                cur.execute(
                    "select metadata, description_sha256, description_excerpt, requirement_tags "
                    "from opportunities where external_id = '100'"
                )
                row = cur.fetchone()
                self.assertNotIn("payload", row["metadata"])
                self.assertEqual(row["metadata"]["facts"]["provider_metadata"], {"applicants": 12})
                self.assertEqual(len(row["description_sha256"]), 64)
                self.assertLessEqual(len(row["description_excerpt"]), 500)
                self.assertEqual(row["requirement_tags"], ["swift", "uikit"])
                cur.execute("select count(*) as n from applications")
                self.assertEqual(cur.fetchone()["n"], 1)
                cur.execute("select metadata from automation_runs where run_key = 'acme-run-1'")
                run_metadata = cur.fetchone()["metadata"]
                self.assertNotIn("payload", run_metadata)
                self.assertEqual(len(run_metadata["payload_sha256"]), 64)
            self.assertIsNotNone(store.verify_run("acme-run-1"))
            self.assertIsNone(store.verify_run("missing"))

            items = {
                Path(item.path).name: item
                for item in plan_prune(store, [discovered, evaluated], min_age=timedelta(0))
            }
            self.assertEqual(items["a.evaluated.payload.json"].action, "delete")
            self.assertEqual(items["a.deduped.payload.json"].action, "delete")

    def test_committed_run_is_visible_to_another_connection(self) -> None:
        idle = self._write("c.payload.json", payload("acme-run-commit", evaluated=False))
        nested = self._write("d.payload.json", payload("acme-run-nested", evaluated=False))
        with connect_test() as writer, connect_test() as reader:
            store = PostgresJobStore(writer)
            # On an idle connection the run is its own transaction and is committed on return.
            store.upsert_run_payload("acme", str(idle))
            self.assertIsNotNone(PostgresJobStore(reader).verify_run("acme-run-commit"))
            reader.rollback()
            # Inside an open transaction the run is only a savepoint until the store commits.
            with writer.cursor() as cur:
                cur.execute("select 1")
            store.upsert_run_payload("acme", str(nested))
            self.assertIsNone(PostgresJobStore(reader).verify_run("acme-run-nested"))
            reader.rollback()
            store.commit()
            self.assertIsNotNone(PostgresJobStore(reader).verify_run("acme-run-nested"))

    def test_payload_hash_is_recorded_once_for_runs_stored_without_one(self) -> None:
        path = self._write("h.payload.json", payload("acme-run-hash", evaluated=True))
        with connect_test() as conn:
            store = PostgresJobStore(conn)
            store.upsert_run_payload("acme", str(path))
            with conn.cursor() as cur:
                cur.execute(
                    "update automation_runs set metadata = metadata - 'payload_sha256' "
                    "where run_key = 'acme-run-hash'"
                )
            self.assertIsNone(store.verify_run("acme-run-hash")["payload_sha256"])
            self.assertTrue(store.record_payload_sha256("acme-run-hash", "a" * 64))
            self.assertEqual(store.verify_run("acme-run-hash")["payload_sha256"], "a" * 64)
            self.assertFalse(store.record_payload_sha256("acme-run-hash", "b" * 64))
            self.assertEqual(store.verify_run("acme-run-hash")["payload_sha256"], "a" * 64)

    def test_documents_find_organizations_with_non_ascii_names(self) -> None:
        with connect_test() as conn:
            with conn.cursor() as cur:
                for name, key in (("Квітка", ""), ("Nordwerk OÜ", "nordwerk o")):
                    cur.execute(
                        "insert into organizations(name, normalized_name) values (%s, %s)",
                        (name, key or "arbium"),
                    )
            for name in ("Квітка", "Nordwerk OÜ"):
                document = put_document(conn, kind="cover_letter", body=f"Hello {name}", organization=name)
                self.assertEqual(
                    [item["id"] for item in list_documents(conn, organization=name)], [document["id"]]
                )
            with self.assertRaises(ValueError):
                put_document(conn, kind="cover_letter", body="x", organization="Невідома")

    def test_shared_automation_state(self) -> None:
        with connect_test() as conn:
            state = PostgresAutomationStateStore(conn)
            state.upsert_source_items(
                "upwork", [{"external_id": "m1", "subject": "Alert", "raw_text": "body"}]
            )
            pending = state.pending_source_items("upwork", "evaluation")
            self.assertEqual([row["external_id"] for row in pending], ["m1"])
            state.mark_source_stage("upwork", "email", "m1", "evaluated")
            self.assertEqual(state.pending_source_items("upwork", "evaluation"), [])
            self.assertTrue(state.reserve_email("key-1", "upwork", "run-x", "to@example.invalid", "Report"))
            self.assertFalse(state.reserve_email("key-1", "upwork", "run-x", "to@example.invalid", "Report"))
            state.mark_email_failed("key-1", "smtp down")
            self.assertTrue(state.reserve_email("key-1", "upwork", "run-x", "to@example.invalid", "Report"))
            state.mark_email_sent("key-1")
            self.assertFalse(state.reserve_email("key-1", "upwork", "run-x", "to@example.invalid", "Report"))
            state.record_run_event("upwork", "run-x", "test_event", "hello")
            with conn.cursor() as cur:
                cur.execute("select raw_text, body_sha256 from source_items where external_id = 'm1'")
                row = cur.fetchone()
                self.assertIsNone(row["raw_text"])
                self.assertEqual(len(row["body_sha256"]), 64)
                cur.execute(
                    "select status, attempts from email_notifications where idempotency_key = 'key-1'"
                )
                self.assertEqual(dict(cur.fetchone()), {"status": "sent", "attempts": 2})

    def test_documents_and_record_application(self) -> None:
        with connect_test() as conn:
            first = put_document(conn, kind="cover_letter", body="Hello", source_key="k1", status="draft")
            second = put_document(conn, kind="cover_letter", body="Hello v2", source_key="k1", status="sent")
            self.assertEqual(first["id"], second["id"])
            self.assertTrue(second["verified"])
            with self.assertRaises(ValueError):
                put_document(conn, kind="unknown", body="x")
            with self.assertRaises(ValueError):
                record_application(conn, {"organization": "Acme", "title": "Engineer"})
            record = {
                "confirmed": True,
                "organization": "Acme Mobile",
                "title": "Mobile Engineer",
                "provider": "linkedin",
                "external_id": "linkedin:555",
                "external_id_aliases": ["ats:req-9"],
                "applied_at": "2026-11-08",
                "salary_requested_min": 65000,
                "salary_requested_max": 75000,
                "salary_requested_currency": "EUR",
            }
            one = record_application(conn, {**record, "job_text": "Posting text " * 20})
            self.assertTrue(one["stored_job_text"])
            two = record_application(conn, {**record, "external_id": "ats:req-9", "external_id_aliases": []})
            self.assertEqual(one["application_id"], two["application_id"])
            self.assertEqual(one["inserted_events"], 1)
            self.assertEqual(two["inserted_events"], 0)
            self.assertEqual(two["readback"]["applications_for_opportunity"], 1)

    def test_cli_documents_prune_and_compact(self) -> None:
        (self.root / "config").mkdir()
        (self.root / "config/jobsearch.toml").write_text(
            'schema_version = 1\n[store]\nbackend = "postgres"\nprune_min_age_hours = 0\n',
            encoding="utf-8",
        )
        note = self.root / "notes/company.md"
        note.parent.mkdir()
        note.write_text("# Company notes", encoding="utf-8")
        report = self.root / "outputs/reports/2026-11-23-job-search.md"
        report.parent.mkdir(parents=True)
        report.write_text("# Report body", encoding="utf-8")
        final = self._write("x.evaluated.payload.json", payload("acme-run-2", evaluated=True))
        with connect_test() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into automation_runs(run_key, metadata) values ('legacy-run', %s::jsonb)",
                    (json.dumps({"payload": {"big": "x" * 1000}}),),
                )
            conn.commit()
        env = {
            "JOBTRACKER_DATABASE_URL": os.environ["SUPABASE_TEST_DB_URL"],
            "JOBTRACKER_STORE_CONNECTOR": "postgres_direct",
        }
        with mock.patch.dict(os.environ, env):
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(
                    [
                        "documents",
                        "put",
                        "--root",
                        str(self.root),
                        "--kind",
                        "company_notes",
                        "--file",
                        str(note),
                        "--delete-local",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(out.getvalue())["deleted_local"])
            self.assertFalse(note.exists())
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "documents",
                            "put",
                            "--root",
                            str(self.root),
                            "--kind",
                            "report",
                            "--file",
                            str(report),
                            "--status",
                            "final",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    main(
                        [
                            "upsert-run",
                            "--root",
                            str(self.root),
                            "--provider",
                            "acme",
                            "--payload",
                            str(final),
                        ]
                    ),
                    0,
                )
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(
                    main(["prune-local", "--root", str(self.root), "--min-age-hours", "0", "--apply"]), 0
                )
            pruned = json.loads(out.getvalue())
            self.assertEqual(pruned["applied"]["deleted"], 2)
            self.assertFalse(final.exists())
            self.assertFalse(report.exists())

            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["compact-db", "--root", str(self.root)]), 0)
            self.assertGreater(json.loads(out.getvalue())["before"]["runs_payload_chars"], 0)
            with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                self.assertEqual(main(["compact-db", "--root", str(self.root), "--apply"]), 2)
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(
                    [
                        "compact-db",
                        "--root",
                        str(self.root),
                        "--apply",
                        "--backup-confirmed",
                        "--drop-unretained-texts",
                    ]
                )
            self.assertEqual(code, 0)
            compacted = json.loads(out.getvalue())
            self.assertEqual(compacted["after"]["runs_payload_chars"], 0)
            self.assertEqual(compacted["payload_copies_removed"]["automation_runs"], 1)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(test_db_reachable(), SKIP_REASON)
class ProbeAgainstDatabaseTests(unittest.TestCase):
    def test_direct_connector_is_reported_available(self) -> None:
        from jobtracker.probe import probe_environment

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / "config/jobsearch.toml").write_text(
                'schema_version = 1\n[store]\nbackend = "postgres"\n',
                encoding="utf-8",
            )
            env = {
                "JOBTRACKER_DATABASE_URL": os.environ["SUPABASE_TEST_DB_URL"],
                "JOBTRACKER_STORE_CONNECTOR": "postgres_direct",
            }
            with mock.patch.dict(os.environ, env):
                probe = probe_environment(root, timeout=3)
        direct = next(
            item for item in probe["database"]["candidates"] if item["connector"] == "postgres_direct"
        )
        self.assertEqual(direct["status"], "available")
        self.assertTrue(direct["selected"])
        self.assertIn("query succeeded", direct["evidence"])
