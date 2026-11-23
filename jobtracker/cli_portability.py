"""CLI commands for shared documents, confirmed applications, pruning and compaction."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from .app_config.loader import load_app_config
from .portability import prune_local
from .store.compact import excerpt, keep_full_text, normalize_text_retention, sha256_text
from .store.generic.postgres_documents import (
    DOCUMENT_KINDS,
    DOCUMENT_STATUSES,
    get_document,
    list_documents,
    put_document,
    record_application,
)
from .store.registry import canonical_backend, describe_store, open_job_store
from .utils import json_default, normalize_space


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=json_default))


def _config(args: argparse.Namespace):
    return load_app_config(getattr(args, "config", None), root=Path(getattr(args, "root", None) or "."))


def _postgres_store(config):
    if canonical_backend(config.store.get("backend")) != "postgres":
        raise ValueError(
            'This command needs the shared PostgreSQL store; set [store].backend = "postgres". '
            "It never writes to a local fallback."
        )
    return open_job_store(config.store, root=config.root)


def _git_head(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def cmd_documents_put(args: argparse.Namespace) -> int:
    config = _config(args)
    path = config.resolve_path(args.file)
    body = path.read_text(encoding="utf-8")
    try:
        source_key = args.source_key or str(path.resolve().relative_to(config.root.resolve()))
    except ValueError:
        source_key = args.source_key or str(path)
    metadata = json.loads(args.metadata) if args.metadata else {}
    metadata.setdefault("source_path", str(path))
    with _postgres_store(config) as store:
        stored = put_document(
            store.conn,
            kind=args.kind,
            body=body,
            title=args.title or path.stem,
            status=args.status,
            source_key=source_key,
            content_format="markdown" if path.suffix.lower() in {".md", ".markdown"} else "text",
            organization=args.organization,
            organization_id=args.organization_id,
            opportunity_id=args.opportunity_id,
            application_id=args.application_id,
            parent_id=args.parent_id,
            base_profile_sha=args.base_profile_sha or _git_head(config.root),
            created_by=args.created_by,
            metadata=metadata,
        )
    deleted = False
    if args.delete_local and stored.get("verified") and stored.get("content_sha256") == sha256_text(body):
        path.unlink()
        deleted = True
    _print_json(
        {
            "document": stored,
            "store": describe_store(config.store, root=config.root),
            "deleted_local": deleted,
        }
    )
    return 0


def cmd_documents_list(args: argparse.Namespace) -> int:
    config = _config(args)
    with _postgres_store(config) as store:
        rows = list_documents(
            store.conn, kind=args.kind, status=args.status, organization=args.organization, limit=args.limit
        )
    _print_json({"documents": rows, "count": len(rows)})
    return 0


def cmd_documents_get(args: argparse.Namespace) -> int:
    config = _config(args)
    with _postgres_store(config) as store:
        row = get_document(store.conn, document_id=args.id, source_key=args.source_key, with_body=True)
    if not row:
        raise ValueError("Document not found")
    if args.output:
        output = config.resolve_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(row["body"], encoding="utf-8")
        row = {key: value for key, value in row.items() if key != "body"} | {"written_to": str(output)}
    _print_json(row)
    return 0


def cmd_record_application(args: argparse.Namespace) -> int:
    config = _config(args)
    record = json.loads(config.resolve_path(args.file).read_text(encoding="utf-8"))
    if args.job_text_file:
        job_text_path = config.resolve_path(args.job_text_file)
        record["job_text"] = job_text_path.read_text(encoding="utf-8")
        record.setdefault("job_text_source", str(job_text_path.name))
    if args.dry_run:
        _print_json({"dry_run": True, "record": record})
        return 0
    with _postgres_store(config) as store:
        result = record_application(store.conn, record)
    _print_json({**result, "store": describe_store(config.store, root=config.root)})
    return 0


def cmd_prune_local(args: argparse.Namespace) -> int:
    config = _config(args)
    with _postgres_store(config) as store:
        result = prune_local(config, store, min_age_hours=args.min_age_hours, apply=args.apply)
    if not args.verbose:
        result["items"] = [item for item in result["items"] if item["action"] == "delete"][:200]
    _print_json(result)
    return 0


def _compact_report(conn: Any) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select
              (select pg_database_size(current_database())) as database_bytes,
              (select coalesce(sum(length((metadata -> 'payload')::text)), 0) from automation_runs) as runs_payload_chars,
              (select coalesce(sum(length((metadata -> 'payload')::text)), 0) from opportunities) as opportunities_payload_chars,
              (select coalesce(sum(length((metadata -> 'payload')::text)), 0) from source_items) as source_items_payload_chars,
              (select coalesce(sum(length((metadata -> 'payload')::text)), 0) from evaluations) as evaluations_payload_chars,
              (select coalesce(sum(length((metadata -> 'payload')::text)), 0) from applications) as applications_payload_chars,
              (select count(*) from source_items where raw_text is not null) as source_items_with_raw_text,
              (select coalesce(sum(length(raw_text)), 0) from source_items) as source_items_raw_chars,
              (select count(*) from opportunity_texts) as retained_texts
            """
        )
        return dict(cur.fetchone())


def _backfill_texts(conn: Any, policy: str) -> dict[str, int]:
    """Copy job texts into opportunity_texts per policy and fill card hashes/excerpts."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select si.id as source_item_id, si.external_id, si.raw_text, si.opportunity_id,
                   exists(select 1 from applications a where a.opportunity_id = si.opportunity_id) as has_application,
                   (select jsonb_build_object(
                      'recommendation', e.recommendation, 'priority', e.priority,
                      'verdict', e.verdict, 'action_next', e.action_next)
                    from evaluations e where e.opportunity_id = si.opportunity_id
                    order by e.evaluated_at desc limit 1) as evaluation
            from source_items si
            where si.raw_text is not null
            """
        )
        rows = cur.fetchall()
    retained = 0
    cards = 0
    for row in rows:
        text = row["raw_text"]
        digest = sha256_text(normalize_space(text))
        item = {
            "application": {"x": 1} if row["has_application"] else None,
            "evaluation": row["evaluation"] or {},
        }
        reason = keep_full_text(item, policy) if row["opportunity_id"] else None
        with conn.cursor() as cur:
            cur.execute(
                "update source_items set body_sha256 = coalesce(body_sha256, %s) where id = %s",
                (digest, row["source_item_id"]),
            )
            if not row["opportunity_id"]:
                continue
            cur.execute(
                """
                update opportunities
                set description_sha256 = coalesce(description_sha256, %s),
                    description_excerpt = coalesce(description_excerpt, %s)
                where id = %s
                """,
                (digest, excerpt(text), row["opportunity_id"]),
            )
            cards += cur.rowcount
            if reason:
                cur.execute(
                    """
                    insert into opportunity_texts(
                      opportunity_id, content_sha256, body, retention_reason, source_item_external_id, fetched_at
                    )
                    values (%s, %s, %s, %s, %s, now())
                    on conflict(opportunity_id, content_sha256) do nothing
                    """,
                    (row["opportunity_id"], digest, text, f"compact_db:{reason}", row["external_id"]),
                )
                retained += cur.rowcount
    return {"cards_updated": cards, "texts_retained": retained, "texts_scanned": len(rows)}


def cmd_compact_db(args: argparse.Namespace) -> int:
    config = _config(args)
    policy = normalize_text_retention(args.text_retention or config.store.get("text_retention"))
    with _postgres_store(config) as store:
        conn = store.conn
        before = _compact_report(conn)
        result: dict[str, Any] = {"apply": args.apply, "text_retention": policy, "before": before}
        if not args.apply:
            result["next_step"] = (
                "Back up the database (pg_dump), then rerun with --apply --backup-confirmed. "
                "Add --drop-unretained-texts to remove job texts that the policy does not keep."
            )
            _print_json(result)
            return 0
        if not args.backup_confirmed:
            raise ValueError("--apply requires --backup-confirmed after a verified database backup")
        with conn.transaction():
            result["backfill"] = _backfill_texts(conn, policy)
            with conn.cursor() as cur:
                stripped = {}
                for table in (
                    "automation_runs",
                    "opportunities",
                    "source_items",
                    "evaluations",
                    "applications",
                ):
                    cur.execute(
                        f"""
                        update {table}
                        set metadata = (metadata - 'payload') || jsonb_build_object('legacy_payload_removed_at', now())
                        where metadata ? 'payload'
                        """
                    )
                    stripped[table] = cur.rowcount
                result["payload_copies_removed"] = stripped
                if args.drop_unretained_texts:
                    # Retained texts were copied to opportunity_texts above; everything else
                    # is dropped by policy. With policy "all", unlinked texts are kept.
                    cur.execute(
                        """
                        update source_items set raw_text = null
                        where raw_text is not null
                          and body_sha256 is not null
                          and (%s <> 'all' or opportunity_id is not null)
                        """,
                        (policy,),
                    )
                    result["raw_texts_cleared"] = cur.rowcount
        result["after"] = _compact_report(conn)
        result["note"] = (
            "Disk space is returned to the database after autovacuum; VACUUM FULL is not run here."
        )
    _print_json(result)
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    def common(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--config", help="Path to jobsearch.toml (default: config/jobsearch.toml)")
        parser.add_argument("--root", default=".", help="Project root for relative paths")

    documents = subparsers.add_parser("documents", help="Store and read shared documents (PostgreSQL only)")
    doc_sub = documents.add_subparsers(dest="documents_command", required=True)

    put = doc_sub.add_parser("put", help="Upsert a Markdown/text document by source key and read it back")
    common(put)
    put.add_argument("--kind", required=True, choices=DOCUMENT_KINDS)
    put.add_argument("--file", required=True)
    put.add_argument("--title")
    put.add_argument("--status", default="draft", choices=DOCUMENT_STATUSES)
    put.add_argument("--source-key", help="Stable identity; defaults to the file path relative to the root")
    put.add_argument("--organization", help="Existing organization name to link")
    put.add_argument("--organization-id")
    put.add_argument("--opportunity-id")
    put.add_argument("--application-id")
    put.add_argument("--parent-id", help="Previous version of this document")
    put.add_argument("--base-profile-sha", help="Profile git commit used; defaults to HEAD")
    put.add_argument("--created-by", help="human, claude, codex, ...")
    put.add_argument("--metadata", help="JSON object with small extra facts")
    put.add_argument("--delete-local", action="store_true", help="Delete the file after verified readback")
    put.set_defaults(func=cmd_documents_put)

    lst = doc_sub.add_parser("list", help="List documents")
    common(lst)
    lst.add_argument("--kind", choices=DOCUMENT_KINDS)
    lst.add_argument("--status", choices=DOCUMENT_STATUSES)
    lst.add_argument("--organization")
    lst.add_argument("--limit", type=int, default=50)
    lst.set_defaults(func=cmd_documents_list)

    get = doc_sub.add_parser("get", help="Print or write one document")
    common(get)
    group = get.add_mutually_exclusive_group(required=True)
    group.add_argument("--id")
    group.add_argument("--source-key")
    get.add_argument("--output", help="Write the body to this file")
    get.set_defaults(func=cmd_documents_get)

    record = subparsers.add_parser(
        "record-application", help="Idempotently record a confirmed application from JSON and read it back"
    )
    common(record)
    record.add_argument("--file", required=True, help="JSON record; see Docs/cli.md")
    record.add_argument("--job-text-file", help="Full posting text to keep for this application")
    record.add_argument("--dry-run", action="store_true")
    record.set_defaults(func=cmd_record_application)

    prune = subparsers.add_parser(
        "prune-local", help="Delete local artifacts whose content is verified in the shared database"
    )
    common(prune)
    prune.add_argument("--min-age-hours", type=float, default=24.0)
    prune.add_argument("--apply", action="store_true", help="Delete; without it only a plan is printed")
    prune.add_argument("--verbose", action="store_true", help="Include kept files in the output")
    prune.set_defaults(func=cmd_prune_local)

    compact = subparsers.add_parser(
        "compact-db", help="Remove legacy full-payload copies and apply the job-text retention policy"
    )
    common(compact)
    compact.add_argument("--text-retention", choices=["shortlisted", "all", "none"])
    compact.add_argument("--apply", action="store_true")
    compact.add_argument("--backup-confirmed", action="store_true")
    compact.add_argument("--drop-unretained-texts", action="store_true")
    compact.set_defaults(func=cmd_compact_db)
