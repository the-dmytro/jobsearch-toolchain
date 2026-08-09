from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from ..base import DuplicateMatch, UpsertResult


class SqliteJobStore:
    SCHEMA_VERSION = 1

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute("create table if not exists schema_version (version integer not null)")
            row = conn.execute("select version from schema_version limit 1").fetchone()
            if row is not None and int(row["version"]) > self.SCHEMA_VERSION:
                raise RuntimeError(
                    f"SQLite schema version {row['version']} is newer than supported "
                    f"version {self.SCHEMA_VERSION}"
                )
            if row is None:
                conn.execute("insert into schema_version(version) values (?)", (self.SCHEMA_VERSION,))
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
                  run_key text,
                  provider_slug text not null,
                  external_id text,
                  company text,
                  title text,
                  payload_json text not null
                );
                """
            )
            columns = {
                str(column["name"]) for column in conn.execute("pragma table_info(opportunities)").fetchall()
            }
            if "run_key" not in columns:
                conn.execute("alter table opportunities add column run_key text")
            conn.execute("create index if not exists opportunities_run_key_idx on opportunities(run_key)")
            conn.commit()

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
        with closing(self._connect()) as conn:
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
            conn.execute("delete from opportunities where run_key = ?", (run_key,))
            for item in opportunities:
                conn.execute(
                    """
                    insert into opportunities(run_key, provider_slug, external_id, company, title, payload_json)
                    values (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_key,
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
        with closing(self._connect()) as conn:
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
