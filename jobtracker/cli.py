from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .automation import run_doctor, run_pipeline, scaffold_config
from .automation_state import AutomationStateStore
from .config import load_env_file
from .db import MissingConfigurationError, MissingDependencyError, connect, connect_test
from .dedupe import LocalDedupeIndex, apply_db_dedupe_matches, dedupe_payload
from .gmail_imap import MAIL_FOLDER_ALIASES, MailImapClient, filter_provider_messages, resolve_mail_folder
from .greenhouse_import import import_greenhouse_tracking, summarize_greenhouse_tracking
from .legacy_import import import_legacy_csv, summarize_legacy_csv
from .linkedin_import import import_linkedin_tracking, summarize_linkedin_tracking
from .mail.base import OutgoingMessage
from .mail.generic.smtp import SmtpMailSender
from .migrations import apply_migrations
from .payloads import check_duplicates, export_application_summary, upsert_run_payload
from .provider_fetch import benchmark_providers, collect_provider_run
from .jobboard_run import prepare_jobboard_run
from .upwork_email import parse_upwork_alert_payload
from .utils import json_default, normalize_space, sha256_text, slugify
from .validation import validate_payload


def _print_json(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=json_default))


def cmd_init(args: argparse.Namespace) -> int:
    result = scaffold_config(root=Path(args.root), force=args.force)
    _print_json(result)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    report = run_doctor(
        config_path=args.config,
        root=Path(args.root) if args.root else None,
        skip_network=args.skip_network,
    )
    _print_json(report)
    return 0 if report.get("ok") else 1


def cmd_run(args: argparse.Namespace) -> int:
    now = _parse_datetime_arg(getattr(args, "now", None))
    try:
        result = run_pipeline(
            args.pipeline,
            config_path=args.config,
            root=Path(args.root) if args.root else None,
            fixture_dir=getattr(args, "fixture_dir", None),
            now=now,
            dry_run=args.dry_run,
        )
    except (ValueError, RuntimeError) as exc:
        raise ValueError(str(exc)) from exc
    _print_json(result)
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    with connect() as conn:
        applied = apply_migrations(conn, dry_run=args.dry_run)
    _print_json({"dry_run": args.dry_run, "migrations": applied})
    return 0


def cmd_import_legacy(args: argparse.Namespace) -> int:
    if args.dry_run:
        _print_json(summarize_legacy_csv(args.csv, links_pdf=args.links_pdf))
        return 0
    with connect() as conn:
        result = import_legacy_csv(conn, args.csv, links_pdf=args.links_pdf)
    _print_json(result)
    return 0


def _parse_date_arg(value: str | None):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_datetime_arg(value: str | None):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed


def cmd_import_linkedin_tracking(args: argparse.Namespace) -> int:
    as_of = _parse_date_arg(args.as_of)
    if args.dry_run:
        _print_json(
            summarize_linkedin_tracking(
                jobs_csv=args.jobs_csv,
                active_csv=args.active_csv,
                archived_csv=args.archived_csv,
                as_of=as_of,
            )
        )
        return 0
    with connect() as conn:
        result = import_linkedin_tracking(
            conn,
            jobs_csv=args.jobs_csv,
            active_csv=args.active_csv,
            archived_csv=args.archived_csv,
            as_of=as_of,
        )
    _print_json(result)
    return 0


def cmd_import_greenhouse(args: argparse.Namespace) -> int:
    as_of = _parse_date_arg(args.as_of)
    if args.dry_run:
        _print_json(summarize_greenhouse_tracking(args.csv, as_of=as_of))
        return 0
    with connect() as conn:
        result = import_greenhouse_tracking(conn, csv_path=args.csv, as_of=as_of)
    _print_json(result)
    return 0


def cmd_upsert_run(args: argparse.Namespace) -> int:
    with connect() as conn:
        result = upsert_run_payload(conn, args.provider, args.payload, report_path=args.report)
    _print_json(result)
    return 0


def cmd_check_duplicates(args: argparse.Namespace) -> int:
    with connect() as conn:
        result = check_duplicates(conn, args.provider, args.company, args.title, external_id=args.external_id)
    _print_json({"matches": result})
    return 0


def cmd_export_summary(args: argparse.Namespace) -> int:
    with connect() as conn:
        summary = export_application_summary(conn, args.application_id)
    if args.output:
        Path(args.output).write_text(summary, encoding="utf-8")
    else:
        print(summary)
    return 0


def cmd_db_smoke(args: argparse.Namespace) -> int:
    connector = connect_test if args.test else connect
    with connector() as conn:
        with conn.cursor() as cur:
            cur.execute("select current_database() as database, current_user as user")
            result = cur.fetchone()
            write_result = None
            if args.write_test:
                cur.execute(
                    """
                    insert into providers(slug, name, provider_type, metadata)
                    values (%s, %s, %s, %s::jsonb)
                    on conflict(slug) do update set
                      name = excluded.name,
                      metadata = providers.metadata || excluded.metadata,
                      updated_at = now()
                    returning id, slug
                    """,
                    ("jobtracker_smoke_test", "Jobtracker Smoke Test", "diagnostic", json.dumps({"rolled_back": True})),
                )
                write_result = cur.fetchone()
                conn.rollback()
    _print_json({"target": "SUPABASE_TEST_DB_URL" if args.test else "SUPABASE_DB_URL", "connection": result, "write_test": write_result})
    return 0


def cmd_validate_payload(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    result = validate_payload(payload, provider=args.provider)
    if args.normalized_out:
        Path(args.normalized_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.normalized_out).write_text(json.dumps(result.normalized, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")
    _print_json(result.to_dict())
    return 0 if result.ok else 1


def cmd_build_local_index(args: argparse.Namespace) -> int:
    index = LocalDedupeIndex.from_payload_dir(args.payload_dir, now=args.now)
    _print_json({"payload_dir": args.payload_dir, **index.summary()})
    return 0


def cmd_dedupe_candidates(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    run_key = _payload_run_key(payload)
    index = LocalDedupeIndex.from_payload_dir(
        args.payload_dir,
        now=args.now,
        exclude_paths=[args.payload],
        exclude_run_keys=[run_key] if run_key else None,
    )
    enriched = dedupe_payload(payload, provider=args.provider, index=index)
    if args.include_db:
        matches_by_external_id: dict[str, list[dict]] = {}
        with connect() as conn:
            for item in enriched.get("opportunities") or []:
                if not isinstance(item, dict):
                    continue
                external_id = normalize_space(item.get("external_id"))
                matches = check_duplicates(conn, args.provider, item.get("company"), item.get("title"), external_id=external_id)
                if external_id and matches:
                    matches_by_external_id[external_id] = matches
        enriched = apply_db_dedupe_matches(enriched, matches_by_external_id, exclude_run_keys=[run_key] if run_key else None)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(enriched, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")
    _print_json(enriched)
    return 0


def cmd_discover_mail_folders(args: argparse.Namespace) -> int:
    with MailImapClient() as client:
        folders = client.list_folders()
    resolved = {}
    for provider, aliases in MAIL_FOLDER_ALIASES.items():
        try:
            resolved[provider] = resolve_mail_folder(folders, provider)
        except RuntimeError:
            resolved[provider] = None
    _print_json({"folders": folders, "resolved": resolved, "aliases": MAIL_FOLDER_ALIASES})
    return 0


def cmd_fetch_mail_folder(args: argparse.Namespace) -> int:
    provider = slugify(args.provider)
    explicit_folder = getattr(args, "folder", None) or getattr(args, "label", None)
    with MailImapClient() as client:
        folder = client.resolve_folder(provider, explicit_folder=explicit_folder)
        fetched_items = client.fetch_label_messages(folder, since=args.since, limit=args.limit)
    filter_result = filter_provider_messages(provider, fetched_items) if not args.no_provider_filter else None
    source_items = fetched_items if args.no_provider_filter else filter_result.matched
    store = AutomationStateStore(args.state_db)
    state_result = store.upsert_source_items(provider, source_items)
    skipped = 0 if args.no_provider_filter else filter_result.skipped
    payload = {
        "run": {
            "run_key": args.run_key or f"{provider}-mail-fetch-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "status": "partial",
            "summary": f"Fetched {len(source_items)} matching source messages from {folder}; skipped {skipped} non-matching messages.",
        },
        "source_items": source_items,
        "summary": f"Fetched {len(source_items)} matching source messages from {folder}; skipped {skipped} non-matching messages.",
        "metadata": {
            "mail_folder": folder,
            "fetched_count": len(fetched_items),
            "matched_count": len(source_items),
            "skipped_count": skipped,
            "provider_filter_enabled": not args.no_provider_filter,
            "state": state_result,
        },
    }
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")
    _print_json(payload)
    return 0


def cmd_parse_upwork_alerts(args: argparse.Namespace) -> int:
    source_payload = json.loads(Path(args.source_payload).read_text(encoding="utf-8"))
    payload = parse_upwork_alert_payload(source_payload, run_key=args.run_key, now=args.now)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")
    _print_json(payload)
    return 0


def _smtp_setting(name: str, default: str | None = None) -> str | None:
    return os.getenv(f"JOBTRACKER_{name}") or os.getenv(name) or default


def cmd_send_report_email(args: argparse.Namespace) -> int:
    load_env_file()
    body = Path(args.body_file).read_text(encoding="utf-8")
    to_address = normalize_space(args.to or _smtp_setting("REPORT_EMAIL_TO"))
    if not to_address:
        raise MissingConfigurationError("recipient is required via --to or JOBTRACKER_REPORT_EMAIL_TO.")
    from_address = args.from_address or _smtp_setting("SMTP_FROM") or _smtp_setting("SMTP_USER")
    provider = slugify(args.provider)
    run_key = normalize_space(args.run_key)
    key = args.idempotency_key or sha256_text(f"{provider}\n{run_key}\n{to_address}\n{args.subject}\n{body}")
    store = AutomationStateStore(args.state_db)
    if not store.reserve_email(key, provider=provider, run_key=run_key, to_address=to_address, subject=args.subject):
        _print_json({"sent": False, "skipped": True, "reason": "email idempotency key already reserved or sent", "idempotency_key": key})
        return 0
    try:
        sender = SmtpMailSender(sender=from_address)
        sender.send(OutgoingMessage(sender=from_address or sender.default_sender, recipient=to_address, subject=args.subject, body=body))
    except Exception as exc:
        store.mark_email_failed(key, str(exc))
        raise
    store.mark_email_sent(key)
    _print_json({"sent": True, "idempotency_key": key, "to": to_address, "subject": args.subject})
    return 0


def _payload_run_key(payload: dict) -> str | None:
    run = payload.get("run") if isinstance(payload.get("run"), dict) else {}
    return normalize_space(run.get("run_key") or payload.get("run_key")) or None


def _provider_from_payload(path: Path, payload: dict, explicit_provider: str | None) -> str:
    if explicit_provider:
        return slugify(explicit_provider)
    run_key = _payload_run_key(payload)
    if run_key and "-" in run_key:
        return slugify(run_key.split("-", 1)[0])
    return slugify(path.stem.split(".", 1)[0])


def cmd_sync_pending_runs(args: argparse.Namespace) -> int:
    payload_paths = sorted(Path(args.payload_dir).rglob("*.payload.json"))
    synced = 0
    skipped = 0
    failed: list[dict[str, str]] = []
    if not payload_paths:
        _print_json({"payload_dir": args.payload_dir, "synced": synced, "skipped": skipped, "failed": failed, "dry_run": args.dry_run})
        return 0
    store = AutomationStateStore(args.state_db)
    for payload_path in payload_paths:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        run_key = _payload_run_key(payload)
        if not run_key:
            failed.append({"payload": str(payload_path), "error": "missing run_key"})
            continue
        provider = _provider_from_payload(payload_path, payload, args.provider)
        if args.provider and provider != slugify(args.provider):
            continue
        if store.is_run_db_synced(run_key):
            skipped += 1
            continue
        if args.dry_run:
            skipped += 1
            continue
        try:
            store.mark_run_sync_attempt(provider, run_key, str(payload_path))
            with connect() as conn:
                upsert_run_payload(conn, provider, payload_path)
            store.mark_run_db_synced(provider, run_key, str(payload_path))
            synced += 1
        except Exception as exc:
            store.mark_run_sync_attempt(provider, run_key, str(payload_path), error=str(exc))
            store.record_run_event(provider, run_key, "db_sync_failed", str(exc), {"payload_path": str(payload_path)})
            failed.append({"payload": str(payload_path), "run_key": run_key, "error": str(exc)})
    _print_json({"payload_dir": args.payload_dir, "synced": synced, "skipped": skipped, "failed": failed, "dry_run": args.dry_run})
    return 1 if failed and not args.keep_going else 0


def _cmd_fetch_provider(args: argparse.Namespace, provider_slug: str) -> int:
    now = _parse_datetime_arg(getattr(args, "now", None))
    try:
        if args.dry_run:
            result = collect_provider_run(
                provider_slug,
                conn=None,
                dry_run=True,
                payload_out=args.payload_out,
                fixture_dir=getattr(args, "fixture_dir", None),
                targets_path=getattr(args, "targets", None),
                now=now,
                max_pages=getattr(args, "max_pages", 1),
                detail_limit=getattr(args, "detail_limit", None),
                board_tokens=getattr(args, "board_token", None),
                max_boards=getattr(args, "max_boards", None),
            )
        else:
            with connect() as conn:
                result = collect_provider_run(
                    provider_slug,
                    conn=conn,
                    dry_run=False,
                    payload_out=args.payload_out,
                    fixture_dir=getattr(args, "fixture_dir", None),
                    targets_path=getattr(args, "targets", None),
                    now=now,
                    max_pages=getattr(args, "max_pages", 1),
                    detail_limit=getattr(args, "detail_limit", None),
                    board_tokens=getattr(args, "board_token", None),
                    max_boards=getattr(args, "max_boards", None),
                )
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc
    _print_json(result.to_dict(dry_run=args.dry_run))
    return 0


def cmd_fetch_dou(args: argparse.Namespace) -> int:
    return _cmd_fetch_provider(args, "dou")


def cmd_fetch_workua(args: argparse.Namespace) -> int:
    return _cmd_fetch_provider(args, "workua")


def cmd_fetch_djinni(args: argparse.Namespace) -> int:
    return _cmd_fetch_provider(args, "djinni")


def cmd_fetch_greenhouse_jobs(args: argparse.Namespace) -> int:
    return _cmd_fetch_provider(args, "greenhouse")


def cmd_benchmark_sources(args: argparse.Namespace) -> int:
    now = _parse_datetime_arg(getattr(args, "now", None))
    providers = [item.strip() for item in (args.providers or "").split(",") if item.strip()]
    try:
        result = benchmark_providers(
            providers,
            live=args.live,
            fixture_dir=getattr(args, "fixture_dir", None),
            now=now,
            max_pages=args.max_pages,
            detail_limit=args.detail_limit,
            max_boards=args.max_boards,
        )
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc
    _print_json(result)
    return 0


def cmd_prepare_jobboard_run(args: argparse.Namespace) -> int:
    now = _parse_datetime_arg(getattr(args, "now", None))
    providers = [item.strip() for item in (args.providers or "").split(",") if item.strip()] or None
    try:
        manifest = prepare_jobboard_run(
            profile_slug=args.profile,
            providers=providers,
            output_dir=args.output_dir,
            payload_dir=args.payload_dir,
            include_db=not args.no_db,
            fixture_dir=getattr(args, "fixture_dir", None),
            now=now,
            max_pages=args.max_pages,
            detail_limit=args.detail_limit,
        )
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc
    _print_json(manifest)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobtracker", description="Supabase-backed job search tracking CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate = subparsers.add_parser("migrate", help="Apply SQL migrations")
    migrate.add_argument("--dry-run", action="store_true", help="List pending migrations without applying them")
    migrate.set_defaults(func=cmd_migrate)

    legacy = subparsers.add_parser("import-legacy", help="Import the legacy semicolon-delimited job search CSV")
    legacy.add_argument("--csv", required=True, help="Path to legacy CSV, for example Docs/Tracking/Job search '25.csv")
    legacy.add_argument(
        "--links-pdf",
        help="Optional PDF export containing the clickable vacancy links. Defaults to a same-name .pdf next to the CSV.",
    )
    legacy.add_argument("--dry-run", action="store_true", help="Parse and summarize without writing to DB")
    legacy.set_defaults(func=cmd_import_legacy)

    linkedin = subparsers.add_parser("import-linkedin-tracking", help="Import LinkedIn jobs and application tracker CSVs")
    linkedin.add_argument("--jobs-csv", help="Path to linkedin_jobs.csv. Defaults to Docs/Tracking/linkedin_jobs.csv when present")
    linkedin.add_argument(
        "--active-csv",
        help="Path to linkedin_applications_active.csv. Defaults to Docs/Tracking/linkedin_applications_active.csv when present",
    )
    linkedin.add_argument(
        "--archived-csv",
        help="Path to linkedin_applications_archived.csv. Defaults to Docs/Tracking/linkedin_applications_archived.csv when present",
    )
    linkedin.add_argument("--as-of", help="Anchor date for LinkedIn relative dates like '2mo ago', in YYYY-MM-DD format")
    linkedin.add_argument("--dry-run", action="store_true", help="Parse and summarize without writing to DB")
    linkedin.set_defaults(func=cmd_import_linkedin_tracking)

    greenhouse = subparsers.add_parser("import-greenhouse", help="Import Greenhouse application tracker CSV")
    greenhouse.add_argument("--csv", help="Path to greenhouse.csv. Defaults to Docs/Tracking/greenhouse.csv when present")
    greenhouse.add_argument("--as-of", help="Anchor date for relative dates like '13 days ago', in YYYY-MM-DD format")
    greenhouse.add_argument("--dry-run", action="store_true", help="Parse and summarize without writing to DB")
    greenhouse.set_defaults(func=cmd_import_greenhouse)

    upsert = subparsers.add_parser("upsert-run", help="Upsert one automation run payload")
    upsert.add_argument("--provider", required=True, help="Provider slug, for example linkedin or upwork")
    upsert.add_argument("--payload", required=True, help="Path to normalized automation payload JSON")
    upsert.add_argument("--report", help="Optional Markdown report path to upload/register")
    upsert.set_defaults(func=cmd_upsert_run)

    dupes = subparsers.add_parser("check-duplicates", help="Check whether an opportunity was already seen/applied to")
    dupes.add_argument("--provider", required=True)
    dupes.add_argument("--company")
    dupes.add_argument("--title")
    dupes.add_argument("--external-id")
    dupes.set_defaults(func=cmd_check_duplicates)

    summary = subparsers.add_parser("export-summary", help="Export a Markdown application summary")
    summary.add_argument("--application-id", required=True)
    summary.add_argument("--output")
    summary.set_defaults(func=cmd_export_summary)

    db_smoke = subparsers.add_parser("db-smoke", help="Run a read-only database connection smoke test")
    db_smoke.add_argument("--test", action="store_true", help="Use SUPABASE_TEST_DB_URL instead of SUPABASE_DB_URL")
    db_smoke.add_argument("--write-test", action="store_true", help="Also run a rollback-only write test")
    db_smoke.set_defaults(func=cmd_db_smoke)

    validate = subparsers.add_parser("validate-payload", help="Validate and normalize an automation payload")
    validate.add_argument("--provider", required=True, help="Provider slug, for example linkedin or upwork")
    validate.add_argument("--payload", required=True, help="Path to automation payload JSON")
    validate.add_argument("--normalized-out", help="Optional path to write the normalized payload JSON")
    validate.set_defaults(func=cmd_validate_payload)

    index = subparsers.add_parser("build-local-index", help="Summarize local payload history for fallback dedupe")
    index.add_argument("--payload-dir", default="outputs/automation-payloads", help="Directory containing *.payload.json files")
    index.add_argument("--now", help=argparse.SUPPRESS)
    index.set_defaults(func=cmd_build_local_index)

    dedupe = subparsers.add_parser("dedupe-candidates", help="Enrich a payload with local duplicate/application evidence")
    dedupe.add_argument("--provider", required=True)
    dedupe.add_argument("--payload", required=True)
    dedupe.add_argument("--payload-dir", default="outputs/automation-payloads", help="Directory containing prior *.payload.json files")
    dedupe.add_argument("--output", help="Optional path to write enriched payload JSON")
    dedupe.add_argument("--include-db", action="store_true", help="Also check Supabase for existing opportunities and applications")
    dedupe.add_argument("--now", help=argparse.SUPPRESS)
    dedupe.set_defaults(func=cmd_dedupe_candidates)

    folders = subparsers.add_parser("discover-mail-folders", help="List IMAP folders and resolve job-alert aliases")
    folders.set_defaults(func=cmd_discover_mail_folders)

    labels = subparsers.add_parser("discover-gmail-labels", help="Alias for discover-mail-folders")
    labels.set_defaults(func=cmd_discover_mail_folders)

    def add_mail_fetch_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--provider", required=True, choices=sorted(MAIL_FOLDER_ALIASES), help="Provider whose mail folder should be fetched")
        parser.add_argument("--folder", help="Explicit IMAP folder name. Defaults to discovered job/Provider or Job(s)/Alerts alias.")
        parser.add_argument("--label", help=argparse.SUPPRESS)
        parser.add_argument("--since", help="Optional IMAP SINCE date, for example 12-May-2026")
        parser.add_argument("--limit", type=int, help="Maximum newest messages to fetch before provider filtering")
        parser.add_argument("--no-provider-filter", action="store_true", help="Do not filter mixed-folder messages by provider sender/content")
        parser.add_argument("--state-db", default="outputs/automation-state/state.sqlite")
        parser.add_argument("--run-key")
        parser.add_argument("--output", help="Optional path to write fetched source payload JSON")
        parser.set_defaults(func=cmd_fetch_mail_folder)

    fetch_mail = subparsers.add_parser("fetch-mail-folder", help="Fetch provider messages from an IMAP folder into local source state")
    add_mail_fetch_args(fetch_mail)

    fetch_gmail = subparsers.add_parser("fetch-gmail-label", help="Alias for fetch-mail-folder")
    add_mail_fetch_args(fetch_gmail)

    parse_upwork = subparsers.add_parser("parse-upwork-alerts", help="Parse fetched Upwork alert emails into an automation payload")
    parse_upwork.add_argument("--source-payload", required=True, help="Payload produced by fetch-mail-folder for provider upwork")
    parse_upwork.add_argument("--output", help="Optional path to write parsed automation payload JSON")
    parse_upwork.add_argument("--run-key", help="Run key for the parsed automation payload")
    parse_upwork.add_argument("--now", help=argparse.SUPPRESS)
    parse_upwork.set_defaults(func=cmd_parse_upwork_alerts)

    send_email = subparsers.add_parser("send-report-email", help="Send a report email through SMTP with idempotency")
    send_email.add_argument("--provider", required=True)
    send_email.add_argument("--run-key", required=True)
    send_email.add_argument("--to")
    send_email.add_argument("--from-address")
    send_email.add_argument("--subject", required=True)
    send_email.add_argument("--body-file", required=True)
    send_email.add_argument("--idempotency-key")
    send_email.add_argument("--state-db", default="outputs/automation-state/state.sqlite")
    send_email.set_defaults(func=cmd_send_report_email)

    sync = subparsers.add_parser("sync-pending-runs", help="Upsert local payloads that have not been marked DB-synced")
    sync.add_argument("--payload-dir", default="outputs/automation-payloads", help="Directory containing *.payload.json files")
    sync.add_argument("--provider", help="Optional provider filter")
    sync.add_argument("--state-db", default="outputs/automation-state/state.sqlite")
    sync.add_argument("--dry-run", action="store_true")
    sync.add_argument("--keep-going", action="store_true", help="Return success even if some payloads fail")
    sync.set_defaults(func=cmd_sync_pending_runs)

    def add_fetch_common(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--dry-run", action="store_true", help="Fetch and summarize without writing to DB")
        parser.add_argument("--payload-out", help="Optional path for the normalized payload JSON")
        parser.add_argument("--max-pages", type=int, default=1, help="Maximum listing pages to fetch where applicable")
        parser.add_argument("--detail-limit", type=int, help="Maximum number of unseen jobs to enrich with detail fetches")
        parser.add_argument("--targets", help="Optional provider target TOML path. Defaults to profile/provider_targets.toml or jobtracker/fixtures/provider_targets.toml")
        parser.add_argument("--fixture-dir", help=argparse.SUPPRESS)
        parser.add_argument("--now", help=argparse.SUPPRESS)

    fetch_dou = subparsers.add_parser("fetch-dou", help="Discover iOS jobs from DOU and upsert them as opportunities")
    add_fetch_common(fetch_dou)
    fetch_dou.set_defaults(func=cmd_fetch_dou)

    fetch_workua = subparsers.add_parser("fetch-workua", help="Discover iOS jobs from Work.ua and upsert them as opportunities")
    add_fetch_common(fetch_workua)
    fetch_workua.set_defaults(func=cmd_fetch_workua)

    fetch_djinni = subparsers.add_parser("fetch-djinni", help="Discover iOS jobs from Djinni and upsert them as opportunities")
    add_fetch_common(fetch_djinni)
    fetch_djinni.set_defaults(func=cmd_fetch_djinni)

    fetch_greenhouse = subparsers.add_parser("fetch-greenhouse-jobs", help="Discover iOS jobs from Greenhouse boards and upsert them as opportunities")
    fetch_greenhouse.add_argument("--dry-run", action="store_true", help="Fetch and summarize without writing to DB")
    fetch_greenhouse.add_argument("--payload-out", help="Optional path for the normalized payload JSON")
    fetch_greenhouse.add_argument("--board-token", action="append", help="Explicit Greenhouse board token to query. May be repeated.")
    fetch_greenhouse.add_argument("--max-boards", type=int, help="Maximum number of boards to query")
    fetch_greenhouse.add_argument("--fixture-dir", help=argparse.SUPPRESS)
    fetch_greenhouse.add_argument("--now", help=argparse.SUPPRESS)
    fetch_greenhouse.set_defaults(func=cmd_fetch_greenhouse_jobs)

    benchmark = subparsers.add_parser("benchmark-sources", help="Benchmark discovery collectors in fixture mode or live mode")
    benchmark.add_argument("--providers", required=True, help="Comma-separated provider slugs, for example dou,workua,djinni,greenhouse")
    benchmark.add_argument("--live", action="store_true", help="Use live network fetches instead of bundled fixtures")
    benchmark.add_argument("--detail-limit", type=int, default=2, help="Maximum detail fetches per provider")
    benchmark.add_argument("--max-pages", type=int, default=1, help="Maximum listing pages per provider")
    benchmark.add_argument("--max-boards", type=int, default=2, help="Maximum Greenhouse boards to query")
    benchmark.add_argument("--fixture-dir", help=argparse.SUPPRESS)
    benchmark.add_argument("--now", help=argparse.SUPPRESS)
    benchmark.set_defaults(func=cmd_benchmark_sources)

    prepare_jobboards = subparsers.add_parser(
        "prepare-jobboard-run",
        help="Fetch, validate, and dedupe DOU/Work.ua/Djinni payloads for a profile-specific jobboard triage run",
    )
    prepare_jobboards.add_argument("--profile", required=True, choices=["ios", "data-ml-ai"], help="Profile/search target to run")
    prepare_jobboards.add_argument("--providers", default="dou,workua,djinni", help="Comma-separated providers to fetch")
    prepare_jobboards.add_argument("--output-dir", default="outputs/automation-payloads", help="Directory for manifest and payload artifacts")
    prepare_jobboards.add_argument("--payload-dir", default="outputs/automation-payloads", help="Directory used for local fallback dedupe history")
    prepare_jobboards.add_argument("--max-pages", type=int, default=1, help="Maximum listing pages to fetch where applicable")
    prepare_jobboards.add_argument("--detail-limit", type=int, help="Override provider default detail enrichment limit")
    prepare_jobboards.add_argument("--no-db", action="store_true", help="Skip DB duplicate checks and use only the local fallback index")
    prepare_jobboards.add_argument("--fixture-dir", help=argparse.SUPPRESS)
    prepare_jobboards.add_argument("--now", help=argparse.SUPPRESS)
    prepare_jobboards.set_defaults(func=cmd_prepare_jobboard_run)

    init_cmd = subparsers.add_parser("init", help="Scaffold config/ and profile/ from example templates")
    init_cmd.add_argument("--root", default=".", help="Project root directory")
    init_cmd.add_argument("--force", action="store_true", help="Overwrite existing scaffolded files")
    init_cmd.set_defaults(func=cmd_init)

    doctor = subparsers.add_parser("doctor", help="Validate config, connectors, and profile placeholders")
    doctor.add_argument("--config", help="Path to jobsearch.toml (default: config/jobsearch.toml)")
    doctor.add_argument("--root", help="Project root directory")
    doctor.add_argument("--skip-network", action="store_true", help="Skip DB/IMAP/SMTP and connector network checks")
    doctor.set_defaults(func=cmd_doctor)

    run_cmd = subparsers.add_parser("run", help="Execute a configured pipeline (source -> dedupe -> store -> notify)")
    run_cmd.add_argument("pipeline", help="Pipeline name from config/jobsearch.toml")
    run_cmd.add_argument("--config", help="Path to jobsearch.toml (default: config/jobsearch.toml)")
    run_cmd.add_argument("--root", help="Project root directory")
    run_cmd.add_argument("--dry-run", action="store_true", help="Fetch and dedupe without DB store or notifications")
    run_cmd.add_argument("--fixture-dir", help=argparse.SUPPRESS)
    run_cmd.add_argument("--now", help=argparse.SUPPRESS)
    run_cmd.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (MissingConfigurationError, MissingDependencyError, FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
