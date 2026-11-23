from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .utils import json_default, normalize_space, sha256_text


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=json_default, sort_keys=True)


class AutomationStateStore:
    backend = "sqlite"

    def __init__(self, path: str | Path = "outputs/automation-state/state.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect()) as conn:
            with conn:
                yield conn

    def _init_schema(self) -> None:
        with self._session() as conn:
            conn.executescript(
                """
                create table if not exists source_items (
                  provider text not null,
                  source_type text not null,
                  external_id text not null,
                  source_url text,
                  source_timestamp text,
                  subject text,
                  body_sha256 text,
                  metadata_json text not null default '{}',
                  fetched_at text not null,
                  evaluated_at text,
                  emailed_at text,
                  db_synced_at text,
                  last_error text,
                  updated_at text not null,
                  primary key(provider, source_type, external_id)
                );

                create table if not exists email_outbox (
                  idempotency_key text primary key,
                  provider text,
                  run_key text,
                  to_address text,
                  subject text,
                  status text not null,
                  attempts integer not null default 0,
                  sent_at text,
                  last_error text,
                  metadata_json text not null default '{}',
                  created_at text not null,
                  updated_at text not null
                );

                create table if not exists run_sync_state (
                  run_key text primary key,
                  provider text,
                  payload_path text,
                  db_synced_at text,
                  sync_attempts integer not null default 0,
                  last_error text,
                  updated_at text not null
                );

                create table if not exists run_events (
                  id integer primary key autoincrement,
                  run_key text,
                  provider text,
                  event_type text not null,
                  message text,
                  metadata_json text not null default '{}',
                  created_at text not null
                );
                """
            )

    def upsert_source_items(self, provider: str, items: list[dict[str, Any]]) -> dict[str, int]:
        now = _utc_iso()
        count = 0
        with self._session() as conn:
            for item in items:
                source_type = normalize_space(item.get("source_type")) or "email"
                external_id = normalize_space(
                    item.get("external_id") or item.get("message_id") or item.get("id")
                )
                if not external_id:
                    continue
                body = normalize_space(
                    item.get("raw_text") or item.get("text") or item.get("summary") or item.get("snippet")
                )
                body_sha = sha256_text(body) if body else None
                conn.execute(
                    """
                    insert into source_items(
                      provider, source_type, external_id, source_url, source_timestamp,
                      subject, body_sha256, metadata_json, fetched_at, updated_at
                    )
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    on conflict(provider, source_type, external_id) do update set
                      source_url = coalesce(excluded.source_url, source_items.source_url),
                      source_timestamp = coalesce(excluded.source_timestamp, source_items.source_timestamp),
                      subject = coalesce(excluded.subject, source_items.subject),
                      body_sha256 = coalesce(excluded.body_sha256, source_items.body_sha256),
                      metadata_json = excluded.metadata_json,
                      fetched_at = source_items.fetched_at,
                      updated_at = excluded.updated_at
                    """,
                    (
                        provider,
                        source_type,
                        external_id,
                        normalize_space(item.get("source_url") or item.get("url") or item.get("gmail_link"))
                        or None,
                        normalize_space(
                            item.get("timestamp") or item.get("source_timestamp") or item.get("email_date")
                        )
                        or None,
                        normalize_space(item.get("subject") or item.get("title")) or None,
                        body_sha,
                        _json(item),
                        now,
                        now,
                    ),
                )
                count += 1
        return {"upserted": count}

    def pending_source_items(
        self, provider: str, stage: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        column = {
            "evaluation": "evaluated_at",
            "evaluated": "evaluated_at",
            "email": "emailed_at",
            "emailed": "emailed_at",
            "db": "db_synced_at",
            "db_synced": "db_synced_at",
        }.get(stage)
        if not column:
            raise ValueError(f"Unsupported source stage: {stage}")
        sql = f"""
            select *
            from source_items
            where provider = ? and {column} is null
            order by coalesce(source_timestamp, fetched_at), external_id
        """
        params: list[Any] = [provider]
        if limit is not None:
            sql += " limit ?"
            params.append(limit)
        with self._session() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def mark_source_stage(self, provider: str, source_type: str, external_id: str, stage: str) -> None:
        column = {
            "evaluated": "evaluated_at",
            "emailed": "emailed_at",
            "db_synced": "db_synced_at",
        }.get(stage)
        if not column:
            raise ValueError(f"Unsupported source stage: {stage}")
        now = _utc_iso()
        with self._session() as conn:
            conn.execute(
                f"""
                update source_items
                set {column} = ?, updated_at = ?, last_error = null
                where provider = ? and source_type = ? and external_id = ?
                """,
                (now, now, provider, source_type, external_id),
            )

    def reserve_email(
        self,
        idempotency_key: str,
        provider: str,
        run_key: str,
        to_address: str,
        subject: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        now = _utc_iso()
        with self._session() as conn:
            row = conn.execute(
                "select status from email_outbox where idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if row and row["status"] in {"reserved", "sent"}:
                return False
            if row:
                conn.execute(
                    """
                    update email_outbox
                    set status = 'reserved', attempts = attempts + 1, last_error = null, updated_at = ?
                    where idempotency_key = ?
                    """,
                    (now, idempotency_key),
                )
            else:
                conn.execute(
                    """
                    insert into email_outbox(
                      idempotency_key, provider, run_key, to_address, subject, status,
                      attempts, metadata_json, created_at, updated_at
                    )
                    values (?, ?, ?, ?, ?, 'reserved', 1, ?, ?, ?)
                    """,
                    (
                        idempotency_key,
                        provider,
                        run_key,
                        to_address,
                        subject,
                        _json(metadata or {}),
                        now,
                        now,
                    ),
                )
            return True

    def mark_email_sent(self, idempotency_key: str) -> None:
        now = _utc_iso()
        with self._session() as conn:
            conn.execute(
                """
                update email_outbox
                set status = 'sent', sent_at = ?, updated_at = ?, last_error = null
                where idempotency_key = ?
                """,
                (now, now, idempotency_key),
            )

    def mark_email_failed(self, idempotency_key: str, error: str) -> None:
        now = _utc_iso()
        with self._session() as conn:
            conn.execute(
                """
                update email_outbox
                set status = 'failed', last_error = ?, updated_at = ?
                where idempotency_key = ?
                """,
                (error, now, idempotency_key),
            )

    def pending_runs(self) -> list[dict[str, Any]]:
        """Journaled runs that have not been confirmed in the shared database."""
        with self._session() as conn:
            rows = conn.execute(
                """
                select run_key, provider, payload_path, sync_attempts, last_error, updated_at
                from run_sync_state
                where db_synced_at is null
                order by updated_at
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def is_run_db_synced(self, run_key: str) -> bool:
        with self._session() as conn:
            row = conn.execute(
                "select db_synced_at from run_sync_state where run_key = ?", (run_key,)
            ).fetchone()
        return bool(row and row["db_synced_at"])

    def mark_run_sync_attempt(
        self, provider: str, run_key: str, payload_path: str, error: str | None = None
    ) -> None:
        now = _utc_iso()
        with self._session() as conn:
            conn.execute(
                """
                insert into run_sync_state(run_key, provider, payload_path, sync_attempts, last_error, updated_at)
                values (?, ?, ?, 1, ?, ?)
                on conflict(run_key) do update set
                  provider = excluded.provider,
                  payload_path = excluded.payload_path,
                  sync_attempts = run_sync_state.sync_attempts + 1,
                  last_error = excluded.last_error,
                  updated_at = excluded.updated_at
                """,
                (run_key, provider, payload_path, error, now),
            )

    def mark_run_db_synced(self, provider: str, run_key: str, payload_path: str) -> None:
        now = _utc_iso()
        with self._session() as conn:
            conn.execute(
                """
                insert into run_sync_state(run_key, provider, payload_path, db_synced_at, sync_attempts, updated_at)
                values (?, ?, ?, ?, 1, ?)
                on conflict(run_key) do update set
                  provider = excluded.provider,
                  payload_path = excluded.payload_path,
                  db_synced_at = excluded.db_synced_at,
                  last_error = null,
                  updated_at = excluded.updated_at
                """,
                (run_key, provider, payload_path, now, now),
            )

    def record_run_event(
        self,
        provider: str,
        run_key: str | None,
        event_type: str,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._session() as conn:
            conn.execute(
                """
                insert into run_events(run_key, provider, event_type, message, metadata_json, created_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (run_key, provider, event_type, message, _json(metadata or {}), _utc_iso()),
            )


_STAGE_COLUMNS = {
    "evaluation": "evaluated_at",
    "evaluated": "evaluated_at",
    "email": "emailed_at",
    "emailed": "emailed_at",
    "db": "db_synced_at",
    "db_synced": "db_synced_at",
}
_MARK_COLUMNS = {"evaluated": "evaluated_at", "emailed": "emailed_at", "db_synced": "db_synced_at"}
_HEAVY_STATE_KEYS = frozenset({"raw_text", "text", "html", "body", "body_html"})


class PostgresAutomationStateStore:
    """Shared automation state in PostgreSQL, so every environment sees the same history.

    Uses ``source_items`` processing columns, ``email_notifications`` and
    ``automation_run_events`` from migration 004. Message bodies are never stored here;
    only a SHA-256 of the body is kept for change detection.
    """

    backend = "postgres"

    def __init__(self, conn: Any) -> None:
        self.conn = conn
        self.path = None

    def _provider_id(self, provider: str) -> Any:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                insert into providers(slug, name) values (%s, %s)
                on conflict(slug) do update set updated_at = now()
                returning id
                """,
                (provider, provider.replace("_", " ").replace("-", " ").title()),
            )
            return cur.fetchone()["id"]

    def _run_id(self, run_key: str | None) -> Any:
        if not run_key:
            return None
        with self.conn.cursor() as cur:
            cur.execute("select id from automation_runs where run_key = %s", (run_key,))
            row = cur.fetchone()
        return row["id"] if row else None

    def upsert_source_items(self, provider: str, items: list[dict[str, Any]]) -> dict[str, int]:
        count = 0
        with self.conn.transaction():
            provider_id = self._provider_id(provider)
            for item in items:
                source_type = normalize_space(item.get("source_type")) or "email"
                external_id = normalize_space(
                    item.get("external_id") or item.get("message_id") or item.get("id")
                )
                if not external_id:
                    continue
                body = normalize_space(
                    item.get("raw_text") or item.get("text") or item.get("summary") or item.get("snippet")
                )
                facts = {key: value for key, value in item.items() if key not in _HEAVY_STATE_KEYS}
                with self.conn.cursor() as cur:
                    cur.execute(
                        """
                        insert into source_items(
                          provider_id, source_type, external_id, source_url, title, summary,
                          body_sha256, fetched_at, processing_status, metadata
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, now(), 'fetched', %s::jsonb)
                        on conflict(provider_id, source_type, external_id) where external_id is not null
                        do update set
                          source_url = coalesce(excluded.source_url, source_items.source_url),
                          title = coalesce(excluded.title, source_items.title),
                          body_sha256 = coalesce(excluded.body_sha256, source_items.body_sha256),
                          fetched_at = coalesce(source_items.fetched_at, excluded.fetched_at),
                          metadata = (source_items.metadata - 'payload') || excluded.metadata,
                          updated_at = now()
                        """,
                        (
                            provider_id,
                            source_type,
                            external_id,
                            normalize_space(
                                item.get("source_url") or item.get("url") or item.get("gmail_link")
                            )
                            or None,
                            normalize_space(item.get("subject") or item.get("title")) or None,
                            normalize_space(item.get("summary") or item.get("snippet"))[:500] or None,
                            sha256_text(body) if body else None,
                            _json({"state": compact_state(facts)}),
                        ),
                    )
                count += 1
        return {"upserted": count}

    def pending_source_items(
        self, provider: str, stage: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        column = _STAGE_COLUMNS.get(stage)
        if not column:
            raise ValueError(f"Unsupported source stage: {stage}")
        sql = f"""
            select si.source_type, si.external_id, si.source_url, si.title as subject,
                   si.body_sha256, si.fetched_at, si.evaluated_at, si.emailed_at, si.db_synced_at
            from source_items si
            join providers p on p.id = si.provider_id
            where p.slug = %s and si.fetched_at is not null and si.{column} is null
            order by coalesce(si.source_timestamp, si.fetched_at), si.external_id
        """
        params: list[Any] = [provider]
        if limit is not None:
            sql += " limit %s"
            params.append(limit)
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def mark_source_stage(self, provider: str, source_type: str, external_id: str, stage: str) -> None:
        column = _MARK_COLUMNS.get(stage)
        if not column:
            raise ValueError(f"Unsupported source stage: {stage}")
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                f"""
                update source_items si
                set {column} = now(), processing_status = %s, processing_error = null, updated_at = now()
                from providers p
                where p.id = si.provider_id and p.slug = %s and si.source_type = %s and si.external_id = %s
                """,
                (stage, provider, source_type, external_id),
            )

    def reserve_email(
        self,
        idempotency_key: str,
        provider: str,
        run_key: str,
        to_address: str,
        subject: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    "select status from email_notifications where idempotency_key = %s for update",
                    (idempotency_key,),
                )
                row = cur.fetchone()
                if row and row["status"] in {"reserved", "sent"}:
                    return False
                if row:
                    cur.execute(
                        """
                        update email_notifications
                        set status = 'reserved', attempts = attempts + 1, last_error = null, updated_at = now()
                        where idempotency_key = %s
                        """,
                        (idempotency_key,),
                    )
                    return True
            provider_id = self._provider_id(provider)
            run_id = self._run_id(run_key)
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    insert into email_notifications(
                      provider_id, automation_run_id, idempotency_key, to_address, subject,
                      status, attempts, metadata
                    )
                    values (%s, %s, %s, %s, %s, 'reserved', 1, %s::jsonb)
                    on conflict(idempotency_key) do nothing
                    returning id
                    """,
                    (
                        provider_id,
                        run_id,
                        idempotency_key,
                        to_address,
                        subject,
                        _json({"run_key": run_key, **(metadata or {})}),
                    ),
                )
                return cur.fetchone() is not None

    def mark_email_sent(self, idempotency_key: str) -> None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                """
                update email_notifications
                set status = 'sent', sent_at = now(), last_error = null, updated_at = now()
                where idempotency_key = %s
                """,
                (idempotency_key,),
            )

    def mark_email_failed(self, idempotency_key: str, error: str) -> None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                """
                update email_notifications
                set status = 'failed', last_error = %s, updated_at = now()
                where idempotency_key = %s
                """,
                (error, idempotency_key),
            )

    def is_run_db_synced(self, run_key: str) -> bool:
        return self._run_id(run_key) is not None

    def mark_run_sync_attempt(
        self, provider: str, run_key: str, payload_path: str, error: str | None = None
    ) -> None:
        if error:
            self.record_run_event(provider, run_key, "db_sync_failed", error, {"payload_path": payload_path})

    def mark_run_db_synced(self, provider: str, run_key: str, payload_path: str) -> None:
        self.record_run_event(provider, run_key, "db_synced", None, {"payload_path": payload_path})

    def record_run_event(
        self,
        provider: str,
        run_key: str | None,
        event_type: str,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.conn.transaction():
            provider_id = self._provider_id(provider)
            run_id = self._run_id(run_key)
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    insert into automation_run_events(
                      provider_id, automation_run_id, run_key, event_type, message, metadata
                    )
                    values (%s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (provider_id, run_id, run_key, event_type, message, _json(metadata or {})),
                )


def compact_state(value: dict[str, Any], limit: int = 500) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, str) and len(item) > limit:
            result[key] = item[: limit - 1] + "…"
        elif isinstance(item, (str, int, float, bool)) or item is None:
            result[key] = item
        elif isinstance(item, (list, dict)) and len(_json(item)) <= limit:
            result[key] = item
    return result


@contextmanager
def open_automation_state(store_options: dict[str, Any], *, sqlite_path: str | Path) -> Iterator[Any]:
    """Automation state lives in the configured store; there is no second location.

    ``store.backend = "postgres"`` keeps it in PostgreSQL (shared by every environment);
    ``"sqlite"`` keeps it in the local SQLite state file.
    """
    from .db import MissingConfigurationError
    from .store.registry import canonical_backend, connect_postgres

    backend = canonical_backend(store_options.get("backend"))
    if backend == "postgres":
        with connect_postgres(store_options) as conn:
            yield PostgresAutomationStateStore(conn)
        return
    if backend == "sqlite":
        yield AutomationStateStore(sqlite_path)
        return
    raise MissingConfigurationError(f"Automation state is not supported for store backend {backend!r}")
