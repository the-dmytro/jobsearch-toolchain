from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..base import DuplicateMatch, JobStore, UpsertResult


class SqliteJobStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                create table if not exists automation_runs (
                  run_key text primary key,
                  provider_slug text not null,
                  payload_json text not null,
                  report_path text,
                  created_at text default current_timestamp
                );
                create table if not exists opportunities (
                  id integer primary key autoincrement,
                  provider_slug text not null,
                  external_id text,
                  company text,
                  title text,
                  payload_json text not null
                );
                """
            )

    def upsert_run_payload(
        self,
        provider_slug: str,
        payload_path: str,
        report_path: str | None = None,
    ) -> UpsertResult:
        payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
        run = payload.get("run") or {}
        run_key = str(run.get("run_key") or payload.get("run_key") or f"{provider_slug}-sqlite")
        opportunities = payload.get("opportunities") or payload.get("jobs") or []
        evaluations = sum(1 for item in opportunities if item.get("evaluation"))
        with self._connect() as conn:
            conn.execute(
                """
                insert into automation_runs(run_key, provider_slug, payload_json, report_path)
                values (?, ?, ?, ?)
                on conflict(run_key) do update set
                  provider_slug = excluded.provider_slug,
                  payload_json = excluded.payload_json,
                  report_path = excluded.report_path
                """,
                (run_key, provider_slug, json.dumps(payload), report_path),
            )
            for item in opportunities:
                conn.execute(
                    """
                    insert into opportunities(provider_slug, external_id, company, title, payload_json)
                    values (?, ?, ?, ?, ?)
                    """,
                    (
                        provider_slug,
                        item.get("external_id"),
                        item.get("company"),
                        item.get("title"),
                        json.dumps(item),
                    ),
                )
            conn.commit()
        return UpsertResult(run_key=run_key, opportunities=len(opportunities), evaluations=evaluations)

    def check_duplicates(
        self,
        provider_slug: str,
        company: str | None,
        title: str | None,
        external_id: str | None = None,
    ) -> list[DuplicateMatch]:
        rows: list[DuplicateMatch] = []
        with self._connect() as conn:
            if external_id:
                matches = conn.execute(
                    """
                    select external_id, company, title
                    from opportunities
                    where provider_slug = ? and external_id = ?
                    limit 20
                    """,
                    (provider_slug, external_id),
                ).fetchall()
                for row in matches:
                    rows.append(
                        DuplicateMatch(
                            match_type="exact_external_id",
                            title=row["title"],
                            company=row["company"],
                        )
                    )
            if company and title:
                matches = conn.execute(
                    """
                    select external_id, company, title
                    from opportunities
                    where provider_slug = ? and company = ? and title = ?
                    limit 20
                    """,
                    (provider_slug, company, title),
                ).fetchall()
                for row in matches:
                    rows.append(
                        DuplicateMatch(
                            match_type="exact_company_title",
                            title=row["title"],
                            company=row["company"],
                        )
                    )
        return rows

    def export_application_summary(self, application_id: str) -> str:
        return f"# Application summary\n\n- Application ID: {application_id}\n"
