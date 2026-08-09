from __future__ import annotations

from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def ensure_migrations_table(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists jobtracker_schema_migrations (
              version text primary key,
              applied_at timestamptz not null default now()
            )
            """
        )


def applied_versions(conn: Any) -> set[str]:
    ensure_migrations_table(conn)
    with conn.cursor() as cur:
        cur.execute("select version from jobtracker_schema_migrations")
        return {row["version"] for row in cur.fetchall()}


def apply_migrations(conn: Any, dry_run: bool = False) -> list[str]:
    applied = applied_versions(conn)
    pending = [path for path in migration_files() if path.name not in applied]
    if dry_run:
        return [path.name for path in pending]

    applied_now: list[str] = []
    with conn.transaction():
        for path in pending:
            sql = path.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    "insert into jobtracker_schema_migrations(version) values (%s) on conflict do nothing",
                    (path.name,),
                )
            applied_now.append(path.name)
    return applied_now
