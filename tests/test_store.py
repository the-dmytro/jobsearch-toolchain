"""Tests for the job stores and artifact backends."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

from jobtracker.config import Settings
from jobtracker.store.artifacts import local as local_artifacts
from jobtracker.store.artifacts import supabase_storage
from jobtracker.store.artifacts.local import (
    LocalArtifactStore,
    S3ArtifactStore,
    artifact_store_factory,
    file_sha256,
)
from jobtracker.store.artifacts.supabase_storage import SupabaseArtifactStore, upload_artifact
from jobtracker.store.base import ArtifactRef, DuplicateMatch, UpsertResult
from jobtracker.store.generic.memory import MemoryJobStore
from jobtracker.store.generic.sqlite import SqliteJobStore


def build_payload(*, run_key: str = "acme-2026-04-21", with_evaluation: bool = False) -> dict:
    opportunity = {
        "opportunity_type": "employment",
        "external_id": "job-1",
        "title": "Senior iOS Engineer",
        "company": "Acme Corp",
        "source_url": "https://jobs.example.com/1",
        "apply_url": "https://jobs.example.com/1",
        "source_items": ["acme:job-1"],
    }
    if with_evaluation:
        opportunity["evaluation"] = {"verdict": "Apply", "confidence": "High"}
    return {
        "run": {"run_key": run_key, "status": "completed", "summary": "one role"},
        "source_items": [
            {
                "source_type": "job_posting",
                "external_id": "acme:job-1",
                "source_url": "https://jobs.example.com/1",
                "title": "Senior iOS Engineer",
            }
        ],
        "opportunities": [
            opportunity,
            {
                "opportunity_type": "employment",
                "external_id": "job-2",
                "title": "Staff iOS Engineer",
                "company": "Acme Corp",
                "source_url": "https://jobs.example.com/2",
                "apply_url": "https://jobs.example.com/2",
            },
        ],
        "manual_review_blockers": [],
        "summary": "one role",
    }


def write_payload(directory: Path, payload: dict, name: str = "run.payload.json") -> Path:
    path = directory / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class MemoryJobStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.store = MemoryJobStore()

    def test_upsert_records_run_and_opportunities(self) -> None:
        path = write_payload(self.root, build_payload(with_evaluation=True))

        result = self.store.upsert_run_payload("acme", str(path), report_path="outputs/report.md")

        self.assertIsInstance(result, UpsertResult)
        self.assertEqual(result.run_key, "acme-2026-04-21")
        self.assertEqual(result.opportunities, 2)
        self.assertEqual(result.evaluations, 1)
        self.assertEqual(self.store.runs["acme-2026-04-21"]["provider"], "acme")
        self.assertEqual(self.store.runs["acme-2026-04-21"]["report_path"], "outputs/report.md")
        self.assertEqual([item["external_id"] for item in self.store.opportunities], ["job-1", "job-2"])

    def test_run_key_falls_back_to_a_provider_default(self) -> None:
        path = write_payload(self.root, {"opportunities": []})

        self.assertEqual(self.store.upsert_run_payload("acme", str(path)).run_key, "acme-memory")

    def test_check_duplicates_returns_seeded_matches(self) -> None:
        write_payload(self.root, build_payload())
        self.store.upsert_run_payload("acme", str(self.root / "run.payload.json"))
        match = DuplicateMatch(
            match_type="exact_external_id", title="Senior iOS Engineer", company="Acme Corp"
        )
        self.store.duplicates[("acme", "job-1")] = [match]

        matches = self.store.check_duplicates("acme", None, None, external_id="job-1")

        self.assertEqual(matches, [match])
        self.assertEqual(matches[0].as_dict()["match_type"], "exact_external_id")

    def test_check_duplicates_is_empty_for_unknown_ids(self) -> None:
        self.assertEqual(self.store.check_duplicates("acme", None, None, external_id="nope"), [])

    def test_export_application_summary_is_markdown(self) -> None:
        summary = self.store.export_application_summary("app-1")

        self.assertIn("# Application summary", summary)
        self.assertIn("app-1", summary)


class SqliteJobStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.store = SqliteJobStore(self.root / "state.sqlite")

    def test_schema_is_created_eagerly(self) -> None:
        self.assertTrue((self.root / "state.sqlite").exists())
        with closing(self.store._connect()) as conn:
            version = conn.execute("select version from schema_version").fetchone()["version"]
        self.assertEqual(version, 1)

    def test_upsert_then_check_duplicates_finds_the_opportunity(self) -> None:
        path = write_payload(self.root, build_payload(with_evaluation=True))

        result = self.store.upsert_run_payload("acme", str(path))

        self.assertEqual(result.run_key, "acme-2026-04-21")
        self.assertEqual(result.opportunities, 2)
        self.assertEqual(result.evaluations, 1)

        by_id = self.store.check_duplicates("acme", None, None, external_id="job-1")
        self.assertEqual([match.match_type for match in by_id], ["exact_external_id"])
        self.assertEqual(by_id[0].title, "Senior iOS Engineer")

        by_company_title = self.store.check_duplicates("acme", "Acme Corp", "Senior iOS Engineer")
        self.assertEqual([match.match_type for match in by_company_title], ["exact_company_title"])

    def test_duplicates_are_scoped_to_the_provider(self) -> None:
        self.store.upsert_run_payload("acme", str(write_payload(self.root, build_payload())))

        self.assertEqual(self.store.check_duplicates("other", None, None, external_id="job-1"), [])

    def test_reupserting_the_same_run_key_updates_in_place(self) -> None:
        path = write_payload(self.root, build_payload())

        self.store.upsert_run_payload("acme", str(path))
        self.store.upsert_run_payload("acme", str(path), report_path="outputs/report.md")

        with closing(self.store._connect()) as conn:
            runs = conn.execute("select run_key, report_path from automation_runs").fetchall()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["report_path"], "outputs/report.md")
        with closing(self.store._connect()) as conn:
            opportunity_count = conn.execute("select count(*) from opportunities").fetchone()[0]
        self.assertEqual(opportunity_count, 2)

    def test_schema_version_newer_than_supported_is_rejected(self) -> None:
        db_path = self.root / "future.sqlite"
        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("create table schema_version(version integer not null)")
            conn.execute("insert into schema_version(version) values (99)")
            conn.commit()

        with self.assertRaises(RuntimeError):
            SqliteJobStore(db_path)

    def test_export_application_summary_is_markdown(self) -> None:
        self.assertIn("app-7", self.store.export_application_summary("app-7"))


class LocalArtifactStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.artifact = self.root / "report.md"
        self.artifact.write_text("# iOS triage report\n", encoding="utf-8")

    def test_file_sha256_matches_hashlib(self) -> None:
        expected = hashlib.sha256(self.artifact.read_bytes()).hexdigest()

        self.assertEqual(file_sha256(self.artifact), expected)

    def test_upload_describes_the_file_without_transferring_it(self) -> None:
        ref = LocalArtifactStore().upload(self.artifact)

        self.assertIsInstance(ref, ArtifactRef)
        self.assertEqual(ref.local_path, str(self.artifact))
        self.assertEqual(ref.storage_path, "report.md")
        self.assertEqual(ref.size_bytes, self.artifact.stat().st_size)
        self.assertFalse(ref.uploaded)
        self.assertEqual(ref.as_dict()["backend"], "local")

    def test_explicit_storage_path_is_preserved(self) -> None:
        ref = LocalArtifactStore().upload(self.artifact, storage_path="reports/2026/report.md")

        self.assertEqual(ref.storage_path, "reports/2026/report.md")


def settings(**overrides) -> Settings:
    base = {
        "db_url": None,
        "test_db_url": None,
        "supabase_url": None,
        "secret_key": None,
        "service_role_key": None,
        "storage_bucket": "job-artifacts",
        "artifact_backend": "local",
        "mail_folder_aliases": {},
        "own_report_senders": frozenset(),
        "s3_artifact_bucket": None,
        "s3_artifact_prefix": None,
    }
    base.update(overrides)
    return Settings(**base)


class S3ArtifactStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.artifact = Path(self._temp.name) / "report.md"
        self.artifact.write_text("# iOS triage report\n", encoding="utf-8")

    def test_missing_bucket_is_rejected(self) -> None:
        with mock.patch.object(local_artifacts, "load_settings", return_value=settings()):
            with self.assertRaises(RuntimeError):
                S3ArtifactStore()

    def test_upload_puts_the_object_and_applies_the_prefix(self) -> None:
        client = mock.Mock()
        boto3 = mock.Mock()
        boto3.client.return_value = client

        with mock.patch.object(local_artifacts, "load_settings", return_value=settings()):
            store = S3ArtifactStore(bucket="artifacts", prefix="reports/")
            with mock.patch.dict(sys.modules, {"boto3": boto3}):
                ref = store.upload(self.artifact)

        boto3.client.assert_called_once_with("s3")
        client.put_object.assert_called_once()
        kwargs = client.put_object.call_args.kwargs
        self.assertEqual(kwargs["Bucket"], "artifacts")
        self.assertEqual(kwargs["Key"], "reports/report.md")
        self.assertEqual(kwargs["Body"], self.artifact.read_bytes())
        self.assertTrue(ref.uploaded)
        self.assertEqual(ref.storage_bucket, "artifacts")
        self.assertEqual(ref.as_dict()["backend"], "s3")

    def test_bucket_and_prefix_come_from_settings_when_omitted(self) -> None:
        configured = settings(s3_artifact_bucket="from-settings", s3_artifact_prefix="nested")

        with mock.patch.object(local_artifacts, "load_settings", return_value=configured):
            store = S3ArtifactStore()

        self.assertEqual(store.bucket, "from-settings")
        self.assertEqual(store.prefix, "nested")


class SupabaseArtifactStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.artifact = Path(self._temp.name) / "report.md"
        self.artifact.write_text("# iOS triage report\n", encoding="utf-8")

    def test_unconfigured_credentials_produce_a_warning_ref(self) -> None:
        with mock.patch.object(supabase_storage, "load_settings", return_value=settings()):
            ref = SupabaseArtifactStore().upload(self.artifact)

        self.assertFalse(ref.uploaded)
        self.assertIn("SUPABASE_URL", ref.upload_warning)
        self.assertEqual(ref.storage_bucket, "job-artifacts")
        self.assertEqual(ref.sha256, file_sha256(self.artifact))

    def test_configured_client_uploads_the_bytes(self) -> None:
        bucket = mock.Mock()
        client = mock.Mock()
        client.storage.from_.return_value = bucket
        supabase_module = mock.Mock()
        supabase_module.create_client.return_value = client
        configured = settings(supabase_url="https://project.supabase.co", secret_key="sb-secret")

        with mock.patch.object(supabase_storage, "load_settings", return_value=configured):
            with mock.patch.dict(sys.modules, {"supabase": supabase_module}):
                ref = SupabaseArtifactStore().upload(self.artifact, storage_path="reports/report.md")

        supabase_module.create_client.assert_called_once_with("https://project.supabase.co", "sb-secret")
        client.storage.from_.assert_called_with("job-artifacts")
        bucket.upload.assert_called_once()
        self.assertTrue(ref.uploaded)
        self.assertEqual(ref.storage_path, "reports/report.md")

    def test_upload_falls_back_to_update_when_upload_fails(self) -> None:
        bucket = mock.Mock()
        bucket.upload.side_effect = RuntimeError("already exists")
        client = mock.Mock()
        client.storage.from_.return_value = bucket
        supabase_module = mock.Mock()
        supabase_module.create_client.return_value = client
        configured = settings(supabase_url="https://project.supabase.co", service_role_key="sb-service")

        with mock.patch.object(supabase_storage, "load_settings", return_value=configured):
            with mock.patch.dict(sys.modules, {"supabase": supabase_module}):
                ref = SupabaseArtifactStore().upload(self.artifact)

        bucket.update.assert_called_once()
        self.assertTrue(ref.uploaded)

    def test_upload_artifact_helper_returns_a_plain_dict(self) -> None:
        with mock.patch.object(supabase_storage, "load_settings", return_value=settings()):
            payload = upload_artifact(self.artifact)

        self.assertIsInstance(payload, dict)
        self.assertFalse(payload["uploaded"])
        self.assertEqual(payload["backend"], "supabase")


class ArtifactStoreFactoryTests(unittest.TestCase):
    def test_local_backend(self) -> None:
        with mock.patch.object(local_artifacts, "load_settings", return_value=settings()):
            self.assertIsInstance(artifact_store_factory(), LocalArtifactStore)

    def test_explicit_backend_overrides_settings(self) -> None:
        configured = settings(artifact_backend="supabase")

        with mock.patch.object(local_artifacts, "load_settings", return_value=configured):
            self.assertIsInstance(artifact_store_factory("local"), LocalArtifactStore)

    def test_supabase_backend(self) -> None:
        with mock.patch.object(
            local_artifacts, "load_settings", return_value=settings(artifact_backend="supabase")
        ):
            self.assertIsInstance(artifact_store_factory(), SupabaseArtifactStore)

    def test_unknown_backend_is_rejected(self) -> None:
        with mock.patch.object(local_artifacts, "load_settings", return_value=settings()):
            with self.assertRaises(ValueError):
                artifact_store_factory("carrier-pigeon")


if __name__ == "__main__":
    unittest.main()
