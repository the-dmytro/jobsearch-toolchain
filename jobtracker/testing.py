"""Helpers for tests that need the local PostgreSQL test database.

``connect_test`` only accepts a local ``SUPABASE_TEST_DB_URL`` that differs from the
production URL, so these helpers never touch a real project. Plugin authors can use
them to run their own store or connector tests the same way.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .db import connect_test
from .migrations import apply_migrations

BOOTSTRAP_SQL = Path(__file__).resolve().parent.parent / "db" / "ci" / "plain_postgres_bootstrap.sql"
SKIP_REASON = "SUPABASE_TEST_DB_URL must point at a reachable local test database"


def test_db_reachable() -> bool:
    """True when the local test database answers; used with ``unittest.skipUnless``."""
    if not os.getenv("SUPABASE_TEST_DB_URL"):
        return False
    try:
        with connect_test() as conn, conn.cursor() as cur:
            cur.execute("select 1")
        return True
    except Exception:
        return False


def bootstrap_plain_postgres(conn: Any) -> None:
    """Create the Supabase roles and schemas the migrations expect on plain PostgreSQL."""
    if not BOOTSTRAP_SQL.exists():
        return
    with conn.cursor() as cur:
        cur.execute(BOOTSTRAP_SQL.read_text(encoding="utf-8"))
    conn.commit()


def prepare_test_database() -> None:
    """Bootstrap and migrate the local test database."""
    with connect_test() as conn:
        bootstrap_plain_postgres(conn)
        apply_migrations(conn)


test_db_reachable.__test__ = False  # not a test case for unittest/pytest discovery
