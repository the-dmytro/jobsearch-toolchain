"""Unit tests for explicit persistence, retention rules, replay selection and pruning."""

from __future__ import annotations

import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from pathlib import Path
from unittest import mock

from jobtracker.automation import run_doctor
from jobtracker.automation_state import AutomationStateStore, open_automation_state
from jobtracker.cli import main
from jobtracker.db import MissingConfigurationError
from jobtracker.portability import choose_replay_files, require_shared_store
from jobtracker.retention import apply_prune, classify, plan_prune
from jobtracker.store.compact import compact_facts, keep_full_text, normalize_text_retention, sha256_json
from jobtracker.store.generic.memory import MemoryJobStore
from jobtracker.store.registry import describe_store, enforce_required_backend

POSTGRES_CONFIG = """schema_version = 1

[store]
backend = "postgres"
required_backend = "postgres"
"""


def write_payload(path: Path, run_key: str, *, evaluated: bool = False) -> Path:
    opportunity: dict = {
        "external_id": "1",
        "title": "Engineer",
        "company": "Acme",
        "source_url": "https://x/1",
    }
    if evaluated:
        opportunity["evaluation"] = {"recommendation": "apply"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"run": {"run_key": run_key}, "opportunities": [opportunity]}), encoding="utf-8"
    )
    return path


class CompactRulesTests(unittest.TestCase):
    def test_compact_facts_hashes_heavy_text_and_truncates(self) -> None:
        facts = compact_facts({"raw_text": "x" * 5000, "nested": {"note": "y" * 3000}, "n": 1})
        self.assertNotIn("raw_text", facts)
        self.assertEqual(facts["raw_text_chars"], 5000)
        self.assertEqual(len(facts["raw_text_sha256"]), 64)
        self.assertLessEqual(len(facts["nested"]["note"]), 1000)
        self.assertEqual(facts["n"], 1)

    def test_keep_full_text_policy(self) -> None:
        self.assertEqual(
            keep_full_text({"evaluation": {"recommendation": "Apply"}}, "shortlisted"),
            "evaluation_recommendation",
        )
        self.assertIsNone(keep_full_text({"evaluation": {"recommendation": "Do not apply"}}, "shortlisted"))
        self.assertIsNone(keep_full_text({"evaluation": {"decision": "skip"}}, "shortlisted"))
        self.assertEqual(keep_full_text({"application": {"status": "applied"}}, "shortlisted"), "application")
        self.assertEqual(keep_full_text({}, "all"), "policy_all")
        self.assertIsNone(keep_full_text({"application": {"x": 1}}, "none"))
        with self.assertRaises(ValueError):
            normalize_text_retention("everything")


class ExplicitStoreTests(unittest.TestCase):
    def test_required_backend_refuses_local_store(self) -> None:
        with self.assertRaises(MissingConfigurationError) as caught:
            enforce_required_backend({"backend": "sqlite", "required_backend": "postgres"})
        self.assertIn("silent local fallback", str(caught.exception))
        with mock.patch.dict(os.environ, {"JOBTRACKER_REQUIRED_STORE": "supabase"}):
            with self.assertRaises(MissingConfigurationError):
                enforce_required_backend({"backend": "sqlite"})
            enforce_required_backend({"backend": "postgresql"})

    def test_state_opener_refuses_sqlite_when_postgres_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(MissingConfigurationError):
                with open_automation_state(
                    "sqlite",
                    sqlite_path=Path(temp_dir) / "state.sqlite",
                    store_options={"backend": "postgres", "required_backend": "postgres"},
                ):
                    pass
            with open_automation_state(
                "auto", sqlite_path=Path(temp_dir) / "s.sqlite", store_options={}
            ) as state:
                self.assertEqual(state.backend, "sqlite")

    def test_describe_store_never_leaks_credentials(self) -> None:
        url = "postgresql://user:secret-password@db.example.invalid:5432/postgres"
        with mock.patch.dict(os.environ, {"JOBTRACKER_DATABASE_URL": url}):
            receipt = describe_store({"backend": "supabase"}, root=Path("."))
        self.assertEqual(receipt, {"backend": "postgres", "target": "db.example.invalid", "shared": True})
        self.assertNotIn("secret", json.dumps(receipt))

    def test_upsert_run_journals_explicitly_when_database_unreachable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / "config/jobsearch.toml").write_text(POSTGRES_CONFIG, encoding="utf-8")
            payload = write_payload(root / "outputs/p.payload.json", "acme-2026-11-23", evaluated=True)
            env = {"JOBTRACKER_DATABASE_URL": "postgresql://u:p@127.0.0.1:9/none?connect_timeout=1"}
            with mock.patch.dict(os.environ, env):
                stderr = io.StringIO()
                with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                    code = main(
                        ["upsert-run", "--provider", "acme", "--payload", str(payload), "--root", str(root)]
                    )
                self.assertEqual(code, 2)
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    code = main(
                        [
                            "upsert-run",
                            "--provider",
                            "acme",
                            "--payload",
                            str(payload),
                            "--root",
                            str(root),
                            "--journal-on-db-failure",
                        ]
                    )
                self.assertEqual(code, 3)
                result = json.loads(stdout.getvalue())
                self.assertEqual(result["persistence"], "pending_sync")
                self.assertFalse(result["persisted"])
                doctor = run_doctor(root=root, skip_network=True)
            self.assertEqual(doctor["status"], "action_required")
            self.assertEqual(doctor["checks"]["pending_sync"][0]["run_key"], "acme-2026-11-23")

    def test_sqlite_store_is_reported_as_local(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / "config/jobsearch.toml").write_text(
                'schema_version = 1\n[store]\nbackend = "sqlite"\n', encoding="utf-8"
            )
            payload = write_payload(root / "outputs/p.payload.json", "acme-1")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(
                    ["upsert-run", "--provider", "acme", "--payload", str(payload), "--root", str(root)]
                )
            self.assertEqual(code, 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["store"]["backend"], "sqlite")
            self.assertFalse(result["store"]["shared"])
            self.assertTrue(result["verified"])


class ReplaySelectionTests(unittest.TestCase):
    def test_prefers_journal_then_most_final_variant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized = write_payload(root / "a.normalized.payload.json", "run-1")
            evaluated = write_payload(root / "a.evaluated.payload.json", "run-1", evaluated=True)
            deduped = write_payload(root / "a.deduped.payload.json", "run-1")
            other = write_payload(root / "b.deduped.payload.json", "run-2")
            chosen = choose_replay_files([normalized, evaluated, deduped, other], {})
            self.assertEqual(chosen["run-1"], evaluated)
            self.assertEqual(chosen["run-2"], other)
            chosen = choose_replay_files([normalized, evaluated], {"run-1": str(deduped)})
            self.assertEqual(chosen["run-1"], deduped)


class _VerifyingStore(MemoryJobStore):
    def __init__(self, documents: set[str] | None = None) -> None:
        super().__init__()
        self.documents = documents or set()

    def find_document_by_sha(self, digest: str):
        return {"id": "doc-1"} if digest in self.documents else None


class PruneTests(unittest.TestCase):
    def test_classify(self) -> None:
        self.assertEqual(classify(Path("x.normalized.payload.json")), "normalized")
        self.assertEqual(classify(Path("x.deduped.payload.json")), "deduped")
        self.assertEqual(classify(Path("x.evaluated.payload.json")), "evaluated")
        self.assertEqual(classify(Path("2026-job-search-manifest.json")), "manifest")
        self.assertEqual(classify(Path("x.payload.json")), "raw")
        self.assertEqual(classify(Path("report.md")), "report")

    def test_only_verified_content_is_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = _VerifyingStore()
            stored_final = write_payload(root / "out/a.evaluated.payload.json", "run-1", evaluated=True)
            store.runs["run-1"] = {"payload_sha256": sha256_json(json.loads(stored_final.read_text()))}
            normalized = write_payload(root / "out/a.normalized.payload.json", "run-1")
            changed = root / "out/b.evaluated.payload.json"
            write_payload(changed, "run-1")
            missing = write_payload(root / "out/c.deduped.payload.json", "run-2")
            report = root / "out/reports/r.md"
            report.parent.mkdir(parents=True)
            report.write_text("# Report", encoding="utf-8")
            unknown_report = root / "out/reports/u.md"
            unknown_report.write_text("# Other", encoding="utf-8")
            from jobtracker.store.compact import sha256_text

            store.documents.add(sha256_text("# Report"))
            files = [stored_final, normalized, changed, missing, report, unknown_report]
            items = {Path(item.path).name: item for item in plan_prune(store, files, min_age=timedelta(0))}
            self.assertEqual(items["a.evaluated.payload.json"].action, "delete")
            self.assertEqual(items["a.normalized.payload.json"].action, "delete")
            self.assertEqual(items["b.evaluated.payload.json"].action, "keep")
            self.assertEqual(items["c.deduped.payload.json"].action, "keep")
            self.assertEqual(items["r.md"].action, "delete")
            self.assertEqual(items["u.md"].action, "keep")
            result = apply_prune(list(items.values()), stop_at=[root])
            self.assertEqual(result["deleted"], 3)
            self.assertFalse(stored_final.exists())
            self.assertTrue(changed.exists())
            self.assertTrue(missing.exists())

    def test_recent_files_are_kept(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_payload(Path(temp_dir) / "a.normalized.payload.json", "run-1")
            store = _VerifyingStore()
            store.runs["run-1"] = {}
            os.utime(path, (time.time(), time.time()))
            (item,) = plan_prune(store, [path], min_age=timedelta(hours=1))
            self.assertEqual(item.action, "keep")

    def test_prune_refused_for_local_store(self) -> None:
        config = mock.Mock(store={"backend": "sqlite"})
        with self.assertRaises(ValueError):
            require_shared_store(config)


class StateJournalTests(unittest.TestCase):
    def test_pending_runs_lists_unsynced_journal_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state = AutomationStateStore(Path(temp_dir) / "state.sqlite")
            state.mark_run_sync_attempt("acme", "run-1", "/tmp/a.json", error="down")
            state.mark_run_sync_attempt("acme", "run-2", "/tmp/b.json")
            state.mark_run_db_synced("acme", "run-2", "/tmp/b.json")
            self.assertEqual([row["run_key"] for row in state.pending_runs()], ["run-1"])


if __name__ == "__main__":
    unittest.main()
