"""Tests for the supabase_https transport: SQL rendering and an end-to-end gateway run.

The end-to-end test serves POST /rest/v1/rpc/jobtracker_sql from a local HTTP server
that calls the real migration-008 function on the local test PostgreSQL database.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import threading
import unittest
import uuid
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from jobtracker.automation_state import PostgresAutomationStateStore
from jobtracker.db import MissingConfigurationError, connect_test
from jobtracker.migrations import apply_migrations
from jobtracker.store.generic.postgres import PostgresJobStore
from jobtracker.store.generic.postgres_documents import put_document, record_application
from jobtracker.store.https_sql import (
    HttpsConnection,
    HttpsSqlError,
    connect_https,
    render_literal,
    render_query,
    statement_mode,
)
from jobtracker.store.registry import open_job_store


class RenderingTests(unittest.TestCase):
    def test_literals(self) -> None:
        self.assertEqual(render_literal(None), "NULL")
        self.assertEqual(render_literal(True), "true")
        self.assertEqual(render_literal(3), "3")
        self.assertEqual(render_literal(Decimal("1.50")), "1.50")
        self.assertEqual(render_literal("O'Brien \\ 50%"), "'O''Brien \\ 50%'")
        self.assertEqual(render_literal([]), "'{}'")
        self.assertEqual(render_literal(["a", "b'c"]), "ARRAY['a', 'b''c']")
        self.assertEqual(render_literal(dt.date(2026, 11, 8)), "'2026-11-08'")
        self.assertEqual(render_literal({"k": "v"}), '\'{"k": "v"}\'')
        self.assertEqual(render_literal(uuid.UUID(int=1)), "'00000000-0000-0000-0000-000000000001'")
        with self.assertRaises(ValueError):
            render_literal("bad\x00")

    def test_placeholders_skip_string_literals(self) -> None:
        query = "select %s as a, '%s literal' as b, 100%% as c where x = %s"
        self.assertEqual(
            render_query(query, (1, "y")), "select 1 as a, '%s literal' as b, 100% as c where x = 'y'"
        )
        self.assertEqual(render_query("select '%s'", None), "select '%s'")
        with self.assertRaises(ValueError):
            render_query("select %s", ())
        with self.assertRaises(ValueError):
            render_query("select 1", (1,))

    def test_statement_modes(self) -> None:
        self.assertEqual(statement_mode("  -- note\n select 1"), "rows")
        self.assertEqual(statement_mode("with a as (select 1) select * from a"), "rows")
        self.assertEqual(statement_mode("insert into t values (1) returning id"), "rows")
        self.assertEqual(statement_mode("update t set a = 1"), "exec")
        self.assertEqual(statement_mode("create table t (id int)"), "exec")

    def test_settings_are_explicit(self) -> None:
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SECRET_KEY": ""}, clear=False):
            with mock.patch("jobtracker.store.https_sql.load_env_file"):
                with self.assertRaises(MissingConfigurationError):
                    with connect_https():
                        pass
        env = {
            "SUPABASE_URL": "https://ref.supabase.co",
            "SUPABASE_SECRET_KEY": "",
            "SUPABASE_SERVICE_ROLE_KEY": "",
        }
        with mock.patch.dict(os.environ, env):
            with mock.patch("jobtracker.store.https_sql.load_env_file"):
                with self.assertRaises(MissingConfigurationError):
                    with connect_https():
                        pass


def _db_reachable() -> bool:
    if not os.getenv("SUPABASE_TEST_DB_URL"):
        return False
    try:
        with connect_test() as conn, conn.cursor() as cur:
            cur.execute("select 1")
        return True
    except Exception:
        return False


class _Gateway(BaseHTTPRequestHandler):
    api_key = "test-secret"

    def log_message(self, *args) -> None:  # noqa: D401 - silence test server
        return

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        if self.path != "/rest/v1/rpc/jobtracker_sql":
            self._reply(404, {"code": "PGRST202", "message": "Could not find the function"})
            return
        if self.headers.get("apikey") != self.api_key:
            self._reply(401, {"message": "Invalid API key"})
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        try:
            with connect_test() as conn, conn.cursor() as cur:
                cur.execute("select jobtracker_sql(%s, %s) as result", (body["query"], body["mode"]))
                result = cur.fetchone()["result"]
                conn.commit()
        except Exception as exc:  # report like PostgREST
            self._reply(400, {"code": getattr(exc, "sqlstate", None) or "XX000", "message": str(exc)})
            return
        self._reply(200, result)

    def _reply(self, status: int, payload: object) -> None:
        data = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@unittest.skipUnless(_db_reachable(), "SUPABASE_TEST_DB_URL must point at a reachable database")
class HttpsGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        bootstrap = Path(__file__).resolve().parent.parent / "db" / "ci" / "plain_postgres_bootstrap.sql"
        with connect_test() as conn:
            with conn.cursor() as cur:
                cur.execute(bootstrap.read_text(encoding="utf-8"))
            conn.commit()
            apply_migrations(conn)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Gateway)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        with connect_test() as conn, conn.cursor() as cur:
            cur.execute(
                "truncate table documents, opportunity_texts, email_notifications, automation_run_events, "
                "application_events, evaluations, source_items, automation_runs, artifacts, applications, "
                "opportunities, organizations, providers restart identity cascade"
            )
            conn.commit()
        self.conn = HttpsConnection(self.base_url, _Gateway.api_key)

    def test_store_operations_over_https(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "run.evaluated.payload.json"
            path.write_text(
                json.dumps(
                    {
                        "run": {"run_key": "acme-https-1", "status": "completed"},
                        "source_items": [
                            {
                                "source_type": "job_posting",
                                "external_id": "acme:1",
                                "raw_text": "It's 100% iOS " * 30,
                            }
                        ],
                        "opportunities": [
                            {
                                "external_id": "1",
                                "title": "Senior iOS Engineer",
                                "company": "O'Neil Apps",
                                "source_url": "https://jobs.example.invalid/1",
                                "source_items": ["acme:1"],
                                "evaluation": {"recommendation": "apply", "requirement_tags": ["swift"]},
                                "application": {"status": "applied", "applied_at": "2026-11-20"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            store = PostgresJobStore(self.conn)
            first = store.upsert_run_payload("acme", str(path))
            store.upsert_run_payload("acme", str(path))
        self.assertEqual(first.stored_texts, 1)
        stored = store.verify_run("acme-https-1")
        self.assertEqual(stored["evaluations_count"], 1)
        matches = store.check_duplicates("acme", "O'Neil Apps", "Senior iOS Engineer", external_id="1")
        self.assertTrue(any(match.application_id for match in matches))

        document = put_document(self.conn, kind="note", body="Notes with 'quotes' and 50%", source_key="n1")
        self.assertTrue(document["verified"])
        self.assertEqual(store.find_document_by_sha(document["content_sha256"])["id"], document["id"])

        result = record_application(
            self.conn,
            {"confirmed": True, "organization": "O'Neil Apps", "title": "Mobile", "external_id": "ats:7"},
        )
        again = record_application(
            self.conn,
            {"confirmed": True, "organization": "O'Neil Apps", "title": "Mobile", "external_id": "ats:7"},
        )
        self.assertEqual(result["application_id"], again["application_id"])

        state = PostgresAutomationStateStore(self.conn)
        self.assertTrue(state.reserve_email("k", "acme", "acme-https-1", "to@example.invalid", "Report"))
        self.assertFalse(state.reserve_email("k", "acme", "acme-https-1", "to@example.invalid", "Report"))

        with connect_test() as conn, conn.cursor() as cur:
            cur.execute("select count(*) as n from applications")
            self.assertEqual(cur.fetchone()["n"], 2)
            cur.execute("select count(*) as n from opportunity_texts")
            self.assertEqual(cur.fetchone()["n"], 1)
        self.assertGreater(self.conn.requests, 10)

    def test_errors_are_raised_not_swallowed(self) -> None:
        with self.assertRaises(HttpsSqlError):
            with self.conn.cursor() as cur:
                cur.execute("select * from no_such_table")
        with self.assertRaises(MissingConfigurationError):
            with HttpsConnection(self.base_url, "wrong-key").cursor() as cur:
                cur.execute("select 1")
        unreachable = HttpsConnection("http://127.0.0.1:9", "k", timeout=2)
        with self.assertRaises(MissingConfigurationError):
            with unreachable.cursor() as cur:
                cur.execute("select 1")

    def test_open_job_store_uses_the_configured_https_transport(self) -> None:
        env = {"SUPABASE_URL": self.base_url, "SUPABASE_SECRET_KEY": _Gateway.api_key}
        with (
            mock.patch.dict(os.environ, env),
            mock.patch("jobtracker.store.https_sql.https_settings") as settings,
        ):
            settings.return_value = (self.base_url, _Gateway.api_key)
            with open_job_store(
                {"backend": "postgres", "transport": "supabase_https"}, root=Path(".")
            ) as store:
                self.assertIsInstance(store.conn, HttpsConnection)
                self.assertIsNone(store.verify_run("missing"))


if __name__ == "__main__":
    unittest.main()
