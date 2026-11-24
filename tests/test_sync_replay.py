"""``sync-pending-runs`` commit and hash behaviour, and Unicode organization lookup.

These use in-memory doubles for the store connection, so they run without a database.
The PostgreSQL counterparts live in ``test_portability_db.py``.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

from jobtracker import cli as jobtracker_cli
from jobtracker.automation_state import AutomationStateStore
from jobtracker.store.base import UpsertResult
from jobtracker.store.compact import sha256_json
from jobtracker.store.generic.postgres import PostgresJobStore, _upsert_run_payload
from jobtracker.store.generic.postgres_documents import find_organization, list_documents, put_document


class TransactionalFakeStore:
    """A store whose writes become durable only on ``commit``; ``crash`` models a killed process."""

    backend = "postgres"

    def __init__(self) -> None:
        self.committed: dict[str, dict[str, Any]] = {}
        self.pending: dict[str, dict[str, Any]] = {}
        self.events: list[tuple[str, str]] = []
        self.interrupt_on: str | None = None
        self.rewritten: list[str] = []

    def seed(self, run_key: str, **fields: Any) -> None:
        self.committed[run_key] = {"run_key": run_key, "payload_sha256": None, **fields}

    def upsert_run_payload(self, provider: str, payload_path: str, report_path: str | None = None):
        payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
        run_key = payload["run"]["run_key"]
        self.events.append(("upsert", run_key))
        if run_key == self.interrupt_on:
            raise KeyboardInterrupt
        opportunities = payload.get("opportunities") or []
        evaluations = sum(1 for item in opportunities if item.get("evaluation"))
        self.pending[run_key] = {
            "run_key": run_key,
            "opportunities_count": len(opportunities),
            "evaluations_count": evaluations,
            "payload_sha256": sha256_json(payload),
        }
        self.rewritten.append(run_key)
        return UpsertResult(run_key=run_key, opportunities=len(opportunities), evaluations=evaluations)

    def verify_run(self, run_key: str) -> dict[str, Any] | None:
        self.events.append(("verify", run_key))
        return self.pending.get(run_key) or self.committed.get(run_key)

    def record_payload_sha256(self, run_key: str, payload_sha256: str) -> bool:
        self.events.append(("record_sha", run_key))
        self.pending[run_key] = {**self.committed[run_key], "payload_sha256": payload_sha256}
        return True

    def commit(self) -> None:
        self.events.append(("commit", ""))
        self.committed.update(self.pending)
        self.pending.clear()

    def rollback(self) -> None:
        self.pending.clear()

    def crash(self) -> None:
        """The process dies: everything not committed is gone."""
        self.pending.clear()


def run_payload(run_key: str, *, opportunities: int = 1, evaluated: int = 0) -> dict[str, Any]:
    items = []
    for index in range(opportunities):
        item: dict[str, Any] = {"external_id": f"{run_key}:{index}", "title": f"Role {index}"}
        if index < evaluated:
            item["evaluation"] = {"recommendation": "apply", "score": 7}
        items.append(item)
    return {"run": {"run_key": run_key}, "opportunities": items}


class SyncPendingRunsTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "payloads").mkdir()
        (self.root / "config").mkdir()
        (self.root / "config/jobsearch.toml").write_text(
            'schema_version = 1\n[store]\nbackend = "postgres"\n', encoding="utf-8"
        )
        env = mock.patch.dict("os.environ", {"JOBTRACKER_STORE_CONNECTOR": "postgres_direct"})
        env.start()
        self.addCleanup(env.stop)
        self.state_db = self.root / "state.sqlite"

    def write_payload(self, payload: dict[str, Any]) -> None:
        path = self.root / "payloads" / f"{payload['run']['run_key']}.payload.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

    def synced_run_keys(self) -> set[str]:
        state = AutomationStateStore(self.state_db)
        keys = {f"r-{number}" for number in range(1, 10) if state.is_run_db_synced(f"r-{number}")}
        return keys

    def sync(self, store: TransactionalFakeStore, **overrides: Any) -> tuple[int, dict[str, Any]]:
        @contextmanager
        def fake_open(options, *, root):
            yield store

        namespace = argparse.Namespace(
            payload_dir=str(self.root / "payloads"),
            provider=None,
            state_db=str(self.state_db),
            dry_run=False,
            keep_going=False,
            target_store="postgres",
            root=str(self.root),
            **overrides,
        )
        buffer = io.StringIO()
        with (
            mock.patch.object(jobtracker_cli, "open_job_store", side_effect=fake_open),
            contextlib.redirect_stdout(buffer),
        ):
            code = jobtracker_cli.cmd_sync_pending_runs(namespace)
        return code, json.loads(buffer.getvalue())

    def test_each_run_is_committed_before_it_is_verified_and_marked(self) -> None:
        for number in (1, 2):
            self.write_payload(run_payload(f"r-{number}"))
        store = TransactionalFakeStore()

        code, result = self.sync(store)

        self.assertEqual((code, result["synced"]), (0, 2))
        for run_key in ("r-1", "r-2"):
            order = [kind for kind, key in store.events if key in (run_key, "")]
            write = order.index("upsert")
            self.assertLess(write, order.index("commit", write), "commit must follow the write")
            self.assertLess(
                order.index("commit", write), order.index("verify", write), "verify committed data"
            )
        self.assertEqual(set(store.committed), {"r-1", "r-2"})

    def test_interruption_after_n_runs_leaves_exactly_n_runs_stored_and_marked(self) -> None:
        for number in range(1, 6):
            self.write_payload(run_payload(f"r-{number}"))
        store = TransactionalFakeStore()
        store.interrupt_on = "r-3"  # runs r-1 and r-2 complete first

        with self.assertRaises(KeyboardInterrupt):
            self.sync(store)
        store.crash()

        self.assertEqual(set(store.committed), {"r-1", "r-2"})
        self.assertEqual(self.synced_run_keys(), {"r-1", "r-2"})

        # The next replay picks up exactly the runs that never reached the database.
        store.interrupt_on = None
        code, result = self.sync(store)
        self.assertEqual((code, result["synced"], result["skipped"]), (0, 3, 2))
        self.assertEqual(set(store.committed), {f"r-{number}" for number in range(1, 6)})

    def test_failed_run_is_rolled_back_and_not_marked(self) -> None:
        self.write_payload(run_payload("r-1"))
        store = TransactionalFakeStore()
        with mock.patch.object(store, "verify_run", return_value=None):
            code, result = self.sync(store)

        self.assertEqual(code, 1)
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(self.synced_run_keys(), set())

    def test_run_stored_without_a_hash_records_it_instead_of_rewriting(self) -> None:
        payload = run_payload("r-1", opportunities=3, evaluated=2)
        self.write_payload(payload)
        store = TransactionalFakeStore()
        store.seed("r-1", opportunities_count=3, evaluations_count=2)

        code, result = self.sync(store)

        self.assertEqual((code, result["synced"], result["skipped"], result["hashes_recorded"]), (0, 0, 1, 1))
        self.assertEqual(store.rewritten, [])
        self.assertEqual(store.committed["r-1"]["payload_sha256"], sha256_json(payload))
        self.assertEqual(self.synced_run_keys(), {"r-1"})

    def test_run_stored_without_a_hash_but_with_different_counts_is_rewritten(self) -> None:
        self.write_payload(run_payload("r-1", opportunities=3, evaluated=2))
        store = TransactionalFakeStore()
        store.seed("r-1", opportunities_count=2, evaluations_count=2)

        code, result = self.sync(store)

        self.assertEqual((code, result["synced"], result["hashes_recorded"]), (0, 1, 0))
        self.assertEqual(store.rewritten, ["r-1"])

    def test_database_run_with_more_evaluations_is_still_a_conflict(self) -> None:
        self.write_payload(run_payload("r-1", opportunities=3, evaluated=1))
        store = TransactionalFakeStore()
        store.seed("r-1", opportunities_count=3, evaluations_count=3)

        code, result = self.sync(store)

        self.assertEqual(code, 1)
        self.assertEqual([item["run_key"] for item in result["conflicts"]], ["r-1"])
        self.assertEqual(store.rewritten, [])
        self.assertEqual(self.synced_run_keys(), set())


class RecordingConnection:
    """Records the order of statements and transaction boundaries."""

    def __init__(self) -> None:
        self.log: list[str] = []
        self.commits = 0

    @contextmanager
    def transaction(self):
        self.log.append("begin")
        yield
        self.log.append("end")

    def cursor(self):
        return RecordingCursor(self)

    def commit(self) -> None:
        self.commits += 1


class RecordingCursor:
    rowcount = 1

    def __init__(self, conn: RecordingConnection) -> None:
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, query: str, params: Any = None) -> None:
        self.conn.log.append(" ".join(query.split())[:24])

    def fetchone(self) -> dict[str, str]:
        return {"id": "id-1"}

    def fetchall(self) -> list[dict[str, str]]:
        return []


class PostgresStoreTransactionTests(unittest.TestCase):
    def test_provider_row_is_written_inside_the_run_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "r-1.payload.json"
            path.write_text(json.dumps(run_payload("r-1", opportunities=0)), encoding="utf-8")
            conn = RecordingConnection()
            _upsert_run_payload(conn, "acme", path)
        self.assertEqual(conn.log[0], "begin")
        self.assertTrue(conn.log[1].startswith("insert into providers"))

    def test_store_commit_commits_the_connection(self) -> None:
        conn = RecordingConnection()
        PostgresJobStore(conn).commit()
        self.assertEqual(conn.commits, 1)


class UnicodeOrganizationTests(unittest.TestCase):
    """Organization names with letters outside a-z0-9 must be found by their stored name."""

    NAMES = ("Квітка", "Nordwerk OÜ", "Acme")

    def make_conn(self):
        names = {name: f"org-{index}" for index, name in enumerate(self.NAMES)}
        # What the existing rows carry: the ASCII-only normalization (empty or truncated).
        normalized = {"acme": "org-2", "nordwerk o": "org-1"}
        test = self

        class Cursor(RecordingCursor):
            def __init__(self, conn) -> None:
                super().__init__(conn)
                self.row = None

            def execute(self, query: str, params: Any = None) -> None:
                flat = " ".join(query.split())
                test.queries.append((flat, params))
                self.row = None
                if "lower(name) = lower" in flat:
                    wanted = params[0].lower()
                    for name, org_id in names.items():
                        if name.lower() == wanted:
                            self.row = {"id": org_id}
                elif "normalized_name = " in flat and "from organizations" in flat:
                    if params[0] in normalized:
                        self.row = {"id": normalized[params[0]]}
                elif flat.startswith("insert into documents"):
                    self.row = {"id": "doc-1", "organization_id": params[11], "content_sha256": params[5]}
                elif flat.startswith("select") and "from documents where id" in flat:
                    stored = next(
                        p for q, p in reversed(test.queries) if q.startswith("insert into documents")
                    )
                    self.row = {"id": params[0], "content_sha256": stored[5]}

            def fetchone(self):
                return self.row

            def fetchall(self):
                return []

        class Conn(RecordingConnection):
            def cursor(self):
                return Cursor(self)

        self.queries: list[tuple[str, Any]] = []
        return Conn()

    def test_find_organization_matches_non_ascii_names(self) -> None:
        conn = self.make_conn()
        self.assertEqual(find_organization(conn, "Квітка"), "org-0")
        self.assertEqual(find_organization(conn, "  квітка "), "org-0")
        self.assertEqual(find_organization(conn, "Nordwerk OÜ"), "org-1")
        self.assertEqual(find_organization(conn, "nordwerk oü"), "org-1")
        self.assertEqual(find_organization(conn, "Acme"), "org-2")

    def test_unknown_non_ascii_name_never_matches_an_empty_normalized_key(self) -> None:
        conn = self.make_conn()
        self.assertIsNone(find_organization(conn, "Невідома"))
        self.assertFalse(any(params and params[0] == "" for _, params in self.queries))

    def test_ascii_fallback_still_finds_punctuation_variants(self) -> None:
        conn = self.make_conn()
        self.assertEqual(find_organization(conn, "acme!"), "org-2")
        self.assertEqual(find_organization(conn, "Nordwerk-O"), "org-1")

    def test_put_document_with_organization_name_resolves_it(self) -> None:
        for name, expected in (("Квітка", "org-0"), ("Nordwerk OÜ", "org-1")):
            with self.subTest(organization=name):
                conn = self.make_conn()
                document = put_document(conn, kind="cover_letter", body="Hello", organization=name)
                self.assertEqual(document.get("organization_id"), expected)

    def test_put_document_reports_unknown_organization(self) -> None:
        conn = self.make_conn()
        with self.assertRaisesRegex(ValueError, "is not in the database"):
            put_document(conn, kind="cover_letter", body="Hello", organization="Невідома")

    def test_list_documents_filters_by_non_ascii_organization(self) -> None:
        conn = self.make_conn()
        self.assertEqual(list_documents(conn, organization="Квітка"), [])
        select = [item for item in self.queries if item[0].startswith("select d.id")]
        self.assertEqual(select[0][1][0], "org-0")
        self.assertEqual(list_documents(conn, organization="Невідома"), [])


if __name__ == "__main__":
    unittest.main()
