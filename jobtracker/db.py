from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

from .config import load_settings


class MissingDependencyError(RuntimeError):
    pass


class MissingConfigurationError(RuntimeError):
    pass


def require_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise MissingDependencyError(
            "psycopg is required for PostgreSQL commands. Install it with `python3 -m pip install -e '.[postgres]'`."
        ) from exc
    return psycopg, dict_row


def _host_from_db_url(db_url: str | None) -> str | None:
    if not db_url:
        return None
    return urlparse(db_url).hostname


def _connection_kind(db_url: str | None) -> str:
    host = _host_from_db_url(db_url) or "[unknown host]"
    if host.endswith(".pooler.supabase.com"):
        return f"Supabase pooler ({host})"
    if host.startswith("db.") and host.endswith(".supabase.co"):
        return f"Supabase direct database endpoint ({host})"
    if host in {"127.0.0.1", "localhost"}:
        return f"local database ({host})"
    return host


def _connect_error_message(setting_name: str, db_url: str, error: BaseException) -> str:
    message = str(error)
    kind = _connection_kind(db_url)
    if "password authentication failed" in message:
        return f"{setting_name} reached {kind}, but authentication failed. Verify the database password and percent-encode URL-special characters in the connection string."
    if any(
        marker in message
        for marker in ("failed to resolve host", "nodename nor servname", "Name or service not known")
    ):
        return f"{setting_name} cannot resolve {kind}. Verify the host and network/DNS access."
    if any(
        marker in message
        for marker in ("No route to host", "Network is unreachable", "Connection refused", "timeout expired")
    ):
        if "Supabase direct database endpoint" in kind:
            return (
                f"{setting_name} uses {kind}, which may be IPv6-only from this network. "
                "Use the Supabase pooler connection string instead."
            )
        return f"{setting_name} cannot reach {kind}. Verify the database is running and reachable."
    return f"{setting_name} failed to connect to {kind}: {message}"


@contextmanager
def connect_url(db_url: str | None, setting_name: str) -> Iterator[Any]:
    if not db_url:
        raise MissingConfigurationError(f"{setting_name} is required for this command.")
    psycopg, dict_row = require_psycopg()
    try:
        with psycopg.connect(db_url, row_factory=dict_row, prepare_threshold=None) as conn:
            yield conn
    except psycopg.OperationalError as exc:
        raise MissingConfigurationError(_connect_error_message(setting_name, db_url, exc)) from exc


@contextmanager
def connect() -> Iterator[Any]:
    settings = load_settings()
    with connect_url(settings.db_url, "JOBTRACKER_DATABASE_URL") as conn:
        yield conn


@contextmanager
def connect_test() -> Iterator[Any]:
    settings = load_settings()
    if not settings.test_db_url:
        raise MissingConfigurationError(
            "SUPABASE_TEST_DB_URL is required for DB integration tests. Tests never fall back to SUPABASE_DB_URL."
        )
    if settings.db_url and settings.test_db_url == settings.db_url:
        raise MissingConfigurationError("SUPABASE_TEST_DB_URL must not be the same as SUPABASE_DB_URL.")
    host = _host_from_db_url(settings.test_db_url)
    if host not in {"127.0.0.1", "localhost"}:
        raise MissingConfigurationError(
            "SUPABASE_TEST_DB_URL must point to the local Supabase test database for write integration tests."
        )
    with connect_url(settings.test_db_url, "SUPABASE_TEST_DB_URL") as conn:
        yield conn


def fetch_one(conn: Any, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
    return dict(row) if row else None


def fetch_all(conn: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    return [dict(row) for row in rows]
