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

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

from jobtracker.automation import run_doctor
from jobtracker.automation_state import AutomationStateStore, open_automation_state
from jobtracker.cli import main
from jobtracker.db import MissingConfigurationError, MissingDependencyError
from jobtracker.portability import choose_replay_files, require_shared_store
from jobtracker.retention import apply_prune, classify, plan_prune
from jobtracker.store.compact import compact_facts, keep_full_text, normalize_text_retention, sha256_json
from jobtracker.store.generic.memory import MemoryJobStore
from jobtracker.store.registry import describe_store

POSTGRES_CONFIG = """schema_version = 1

[store]
backend = "postgres"
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
    def test_state_follows_the_configured_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sqlite_path = Path(temp_dir) / "state.sqlite"
            with open_automation_state({"backend": "sqlite"}, sqlite_path=sqlite_path) as state:
                self.assertEqual(state.backend, "sqlite")
            with self.assertRaises(MissingConfigurationError):
                with open_automation_state({}, sqlite_path=sqlite_path):
                    pass
            with self.assertRaises(MissingConfigurationError):
                with open_automation_state({"backend": "memory"}, sqlite_path=sqlite_path):
                    pass

    def test_describe_store_never_leaks_credentials(self) -> None:
        url = "postgresql://user:secret-password@db.example.invalid:5432/postgres"
        with mock.patch.dict(os.environ, {"JOBTRACKER_DATABASE_URL": url}):
            receipt = describe_store({"backend": "supabase", "connector": "postgres_direct"}, root=Path("."))
        self.assertEqual(
            receipt,
            {
                "backend": "postgres",
                "connector": "postgres_direct",
                "target": "db.example.invalid",
                "shared": True,
            },
        )
        self.assertNotIn("secret", json.dumps(receipt))
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://ref.supabase.co"}):
            receipt = describe_store({"backend": "postgres", "connector": "supabase_https"}, root=Path("."))
        self.assertEqual(receipt["target"], "ref.supabase.co")

    def test_unreachable_database_is_an_error_and_nothing_is_written_locally(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / "config/jobsearch.toml").write_text(POSTGRES_CONFIG, encoding="utf-8")
            payload = write_payload(root / "outputs/p.payload.json", "acme-2026-11-23", evaluated=True)
            env = {
                "JOBTRACKER_DATABASE_URL": "postgresql://u:p@127.0.0.1:9/none?connect_timeout=1",
                "JOBTRACKER_STORE_CONNECTOR": "postgres_direct",
            }
            with mock.patch.dict(os.environ, env):
                stderr = io.StringIO()
                with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                    code = main(
                        ["upsert-run", "--provider", "acme", "--payload", str(payload), "--root", str(root)]
                    )
            self.assertEqual(code, 2)
            self.assertIn("error:", stderr.getvalue())
            self.assertEqual(sorted(p.name for p in (root / "outputs").iterdir()), ["p.payload.json"])
            with mock.patch.dict(os.environ, env):
                doctor = run_doctor(root=root, skip_network=True)
            self.assertEqual(doctor["checks"]["store"]["backend"], "postgres")
            self.assertEqual(doctor["checks"]["pending_sync"], [])

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

    def test_missing_provider_targets_is_an_error_outside_fixture_mode(self) -> None:
        from jobtracker.sources.registry import _load_targets

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                _load_targets(root=Path(temp_dir))
            self.assertIn("providers", _load_targets(root=Path(temp_dir), fixture_mode=True))


class ReplaySelectionTests(unittest.TestCase):
    def test_prefers_the_most_final_variant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized = write_payload(root / "a.normalized.payload.json", "run-1")
            evaluated = write_payload(root / "a.evaluated.payload.json", "run-1", evaluated=True)
            deduped = write_payload(root / "a.deduped.payload.json", "run-1")
            other = write_payload(root / "b.deduped.payload.json", "run-2")
            chosen = choose_replay_files([normalized, evaluated, deduped, other])
            self.assertEqual(chosen["run-1"], evaluated)
            self.assertEqual(chosen["run-2"], other)
            self.assertEqual(choose_replay_files([normalized, deduped])["run-1"], deduped)


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


class ReplayStateTests(unittest.TestCase):
    def test_pending_runs_lists_failed_replays(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state = AutomationStateStore(Path(temp_dir) / "state.sqlite")
            state.mark_run_sync_attempt("acme", "run-1", "/tmp/a.json", error="down")
            state.mark_run_sync_attempt("acme", "run-2", "/tmp/b.json")
            state.mark_run_db_synced("acme", "run-2", "/tmp/b.json")
            self.assertEqual([row["run_key"] for row in state.pending_runs()], ["run-1"])


if __name__ == "__main__":
    unittest.main()


class SharedTemplateTests(unittest.TestCase):
    def test_connector_comes_only_from_the_environment_variable(self) -> None:
        from jobtracker.app_config.loader import load_app_config
        from jobtracker.app_config.schema import ConfigValidationError
        from jobtracker.automation import scaffold_config

        repo = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            for name in ("jobsearch.example.toml", "jobsearch.shared.example.toml"):
                (root / "config" / name).write_text(
                    (repo / "config" / name).read_text(encoding="utf-8"), encoding="utf-8"
                )
            scaffold_config(root=root, template="shared")
            with mock.patch.dict(os.environ, {"JOBTRACKER_STORE_CONNECTOR": ""}):
                with self.assertRaises(ConfigValidationError) as caught:
                    load_app_config(root=root)
            self.assertIn("probe-environment", str(caught.exception))
            for connector in ("postgres_direct", "supabase_https"):
                with mock.patch.dict(os.environ, {"JOBTRACKER_STORE_CONNECTOR": connector}):
                    config = load_app_config(root=root)
                self.assertEqual(config.store["connector"], connector)
                self.assertEqual(config.store["connector_source"], "JOBTRACKER_STORE_CONNECTOR")
            config_path = root / "config/jobsearch.toml"
            text = config_path.read_text(encoding="utf-8")
            config_path.write_text(
                text.replace('backend = "postgres"', 'backend = "postgres"\nconnector = "x"'),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"JOBTRACKER_STORE_CONNECTOR": "postgres_direct"}):
                with self.assertRaises(ConfigValidationError) as caught:
                    load_app_config(root=root)
            self.assertIn("environment-specific", str(caught.exception))
            config_path.write_text(text, encoding="utf-8")
            (root / "config/jobsearch.local.toml").write_text('[store]\nhosting = "x"\n', encoding="utf-8")
            with mock.patch.dict(os.environ, {"JOBTRACKER_STORE_CONNECTOR": "postgres_direct"}):
                with self.assertRaises(ConfigValidationError):
                    load_app_config(root=root)
            with self.assertRaises(ValueError):
                scaffold_config(root=root, template="nope", force=True)

    def test_connector_variable_is_refused_for_sqlite(self) -> None:
        from jobtracker.app_config.loader import load_app_config
        from jobtracker.app_config.schema import ConfigValidationError

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / "config/jobsearch.toml").write_text(
                'schema_version = 1\n[store]\nbackend = "sqlite"\n', encoding="utf-8"
            )
            with mock.patch.dict(os.environ, {"JOBTRACKER_STORE_CONNECTOR": "postgres_direct"}):
                with self.assertRaises(ConfigValidationError):
                    load_app_config(root=root)
            with mock.patch.dict(os.environ, {"JOBTRACKER_STORE_CONNECTOR": ""}):
                self.assertEqual(load_app_config(root=root).store["backend"], "sqlite")

    def test_connector_must_match_declared_hosting(self) -> None:
        from jobtracker.store.registry import describe_store

        with self.assertRaises(MissingConfigurationError):
            describe_store(
                {"backend": "postgres", "connector": "supabase_https", "hosting": "neon"}, root=Path(".")
            )
        with self.assertRaises(MissingConfigurationError):
            describe_store({"backend": "postgres", "connector": "mysql_magic"}, root=Path("."))
        with self.assertRaises(MissingConfigurationError):
            describe_store({"backend": "postgres"}, root=Path("."))

    def test_environment_scripts_exist_and_are_executable(self) -> None:
        repo = Path(__file__).resolve().parent.parent
        for name in ("setup.sh", "verify.sh"):
            path = repo / "scripts" / "environment" / name
            self.assertTrue(path.exists())
            self.assertTrue(os.access(path, os.X_OK))


class ConnectorIsolationTests(unittest.TestCase):
    """postgres_direct and supabase_https are alternatives: neither is ever used for the other."""

    def test_https_failure_never_tries_direct(self) -> None:
        from jobtracker.store import registry
        from jobtracker.store.connectors import postgres_direct

        env = {
            "SUPABASE_URL": "https://127.0.0.1:9",
            "SUPABASE_SECRET_KEY": "k",
            "JOBTRACKER_DATABASE_URL": "postgresql://u:p@db.example.invalid/x",
        }
        with mock.patch.dict(os.environ, env), mock.patch.object(postgres_direct, "connect") as direct:
            with self.assertRaises(MissingConfigurationError):
                with registry.open_job_store(
                    {"backend": "postgres", "connector": "supabase_https"}, root=Path(".")
                ) as store:
                    store.verify_run("x")
        direct.assert_not_called()

    def test_direct_failure_never_tries_https(self) -> None:
        from jobtracker.store import registry
        from jobtracker.store.connectors import supabase_https as https_sql

        env = {
            "SUPABASE_URL": "https://ref.supabase.co",
            "SUPABASE_SECRET_KEY": "k",
            "JOBTRACKER_DATABASE_URL": "postgresql://u:p@127.0.0.1:9/none?connect_timeout=1",
        }
        with mock.patch.dict(os.environ, env), mock.patch.object(https_sql, "connect_https") as https:
            # Without psycopg installed the direct connector fails earlier, which is also an error.
            with self.assertRaises((MissingConfigurationError, MissingDependencyError)):
                with registry.open_job_store(
                    {"backend": "postgres", "connector": "postgres_direct"}, root=Path(".")
                ):
                    pass
        https.assert_not_called()

    def test_https_does_not_need_or_read_the_database_url(self) -> None:
        from jobtracker.store import https_sql

        env = {
            "SUPABASE_URL": "https://ref.supabase.co",
            "SUPABASE_SECRET_KEY": "k",
            "JOBTRACKER_DATABASE_URL": "",
        }
        with mock.patch.dict(os.environ, env):
            self.assertEqual(https_sql.https_settings(), ("https://ref.supabase.co", "k"))


class ProbeTests(unittest.TestCase):
    def _root(self, temp_dir: str, store: str) -> Path:
        root = Path(temp_dir)
        (root / "config").mkdir()
        (root / "config/jobsearch.toml").write_text(
            f"schema_version = 1\n[store]\n{store}\n", encoding="utf-8"
        )
        return root

    def test_postgres_alone_is_not_evidence_of_supabase(self) -> None:
        from jobtracker.probe import format_probe, probe_environment

        env = {"JOBTRACKER_DATABASE_URL": "", "SUPABASE_URL": "", "JOBTRACKER_STORE_CONNECTOR": ""}
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(os.environ, env):
            root = self._root(temp_dir, 'backend = "postgres"')
            probe = probe_environment(root, timeout=1)
        candidates = {item["connector"]: item for item in probe["database"]["candidates"]}
        self.assertEqual(candidates["supabase_https"]["status"], "not_applicable")
        self.assertEqual(candidates["postgres_direct"]["status"], "not_configured")
        self.assertNotIn("platform", probe)
        self.assertIn("proxy_variables", probe["runtime"])
        self.assertEqual(probe["repository"]["setup_state"], "new")
        self.assertIn("JOBTRACKER_STORE_CONNECTOR is not set", probe["repository"]["config_error"])
        self.assertEqual(probe["repository"]["store"]["backend"], "postgres")
        self.assertIn("supabase_https", format_probe(probe))
        self.assertNotIn(
            "secret", json.dumps(probe).lower().replace("supabase_secret_key", "").replace("secrets", "")
        )

    def test_declared_supabase_hosting_makes_the_https_connector_applicable(self) -> None:
        from jobtracker.probe import probe_environment

        env = {
            "JOBTRACKER_DATABASE_URL": "postgresql://u:hidden-pass@127.0.0.1:9/x",
            "SUPABASE_URL": "https://127.0.0.1:9",
            "SUPABASE_SECRET_KEY": "",
            "JOBTRACKER_STORE_CONNECTOR": "supabase_https",
        }
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(os.environ, env):
            root = self._root(temp_dir, 'backend = "postgres"\nhosting = "supabase"')
            probe = probe_environment(root, timeout=1)
        candidates = {item["connector"]: item for item in probe["database"]["candidates"]}
        self.assertEqual(candidates["postgres_direct"]["status"], "blocked")
        self.assertEqual(candidates["supabase_https"]["status"], "blocked")
        self.assertTrue(candidates["supabase_https"]["selected"])
        self.assertIn('store.hosting = "supabase"', probe["database"]["supabase_evidence"])
        self.assertNotIn("hidden-pass", json.dumps(probe))

    def test_plugin_connectors_join_the_registry(self) -> None:
        from jobtracker.store.connectors import ConnectorInfo, ProbeResult, connector_registry, get_connector

        class FakeConnector:
            info = ConnectorInfo("fake_http", "postgres", "https", "acme", False, ("ACME_URL",), (), "test")

            def connect(self, options):
                raise AssertionError("not used")

            def target(self, options):
                return "acme"

            def probe(self, options, *, timeout):
                return ProbeResult("fake_http", "not_configured", needs=["ACME_URL"])

        connector_registry.register("fake_http")(FakeConnector())
        try:
            self.assertEqual(get_connector("fake_http").info.hosting, "acme")
            from jobtracker.store.registry import describe_store

            receipt = describe_store(
                {"backend": "postgres", "connector": "fake_http", "hosting": "acme"}, root=Path(".")
            )
            self.assertEqual(receipt["target"], "acme")
        finally:
            connector_registry._items.pop("fake_http", None)
