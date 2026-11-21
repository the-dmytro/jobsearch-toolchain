from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .app_config.loader import load_app_config
from .automation import run_doctor, run_pipeline, scaffold_config
from .automation_state import AutomationStateStore
from .calendar.base import CalendarInfo
from .calendar.base import calendar_url as resolve_calendar_url
from .calendar.events import CalendarService, build_reply, ics_to_specs, key_to_uid, settings_from_options
from .calendar.ical import aware, serialize
from .calendar.mail import parse_message
from .calendar.registry import build_calendar_backend
from .calendar.reply import send_reply
from .config import load_env_file
from .db import MissingConfigurationError, MissingDependencyError, connect, connect_test
from .dedupe import LocalDedupeIndex, apply_db_dedupe_matches, dedupe_payload
from .gmail_imap import MAIL_FOLDER_ALIASES, MailImapClient, filter_provider_messages, resolve_mail_folder
from .greenhouse_import import import_greenhouse_tracking, summarize_greenhouse_tracking
from .jobboard_run import prepare_jobboard_run
from .legacy_import import import_legacy_csv, summarize_legacy_csv
from .linkedin_import import import_linkedin_tracking, summarize_linkedin_tracking
from .mail.base import OutgoingMessage
from .mail.generic.smtp import SmtpMailSender
from .mail.registry import build_alert_parser, build_mail_inbox, build_mail_sender
from .migrations import apply_migrations
from .payloads import check_duplicates
from .provider_fetch import benchmark_providers, collect_provider_run
from .sources.registry import source_registry
from .store.registry import open_job_store
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
    return {"ready": 0, "action_required": 1, "error": 2}.get(report.get("status"), 2)


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
    config = load_app_config(getattr(args, "config", None), root=Path(getattr(args, "root", None) or "."))
    payload_path = config.resolve_path(args.payload)
    report_path = str(config.resolve_path(args.report)) if args.report else None
    with open_job_store(config.store, root=config.root) as store:
        result = store.upsert_run_payload(args.provider, str(payload_path), report_path=report_path)
    _print_json(vars(result))
    return 0


def cmd_check_duplicates(args: argparse.Namespace) -> int:
    config = load_app_config(getattr(args, "config", None), root=Path(getattr(args, "root", None) or "."))
    with open_job_store(config.store, root=config.root) as store:
        result = store.check_duplicates(args.provider, args.company, args.title, external_id=args.external_id)
    _print_json({"matches": [match.as_dict() for match in result]})
    return 0


def cmd_export_summary(args: argparse.Namespace) -> int:
    config = load_app_config(getattr(args, "config", None), root=Path(getattr(args, "root", None) or "."))
    with open_job_store(config.store, root=config.root) as store:
        summary = store.export_application_summary(args.application_id)
    if args.output:
        output = config.resolve_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(summary, encoding="utf-8")
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
                    (
                        "jobtracker_smoke_test",
                        "Jobtracker Smoke Test",
                        "diagnostic",
                        json.dumps({"rolled_back": True}),
                    ),
                )
                write_result = cur.fetchone()
                conn.rollback()
    _print_json(
        {
            "target": "SUPABASE_TEST_DB_URL" if args.test else "SUPABASE_DB_URL",
            "connection": result,
            "write_test": write_result,
        }
    )
    return 0


def cmd_validate_payload(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    result = validate_payload(payload, provider=args.provider)
    if args.normalized_out:
        Path(args.normalized_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.normalized_out).write_text(
            json.dumps(result.normalized, indent=2, ensure_ascii=False, default=json_default),
            encoding="utf-8",
        )
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
                matches = check_duplicates(
                    conn, args.provider, item.get("company"), item.get("title"), external_id=external_id
                )
                if external_id and matches:
                    matches_by_external_id[external_id] = matches
        enriched = apply_db_dedupe_matches(
            enriched, matches_by_external_id, exclude_run_keys=[run_key] if run_key else None
        )
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            json.dumps(enriched, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8"
        )
    _print_json(enriched)
    return 0


def cmd_discover_mail_folders(args: argparse.Namespace) -> int:
    with _open_mail_inbox(args) as client:
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
    config = _optional_app_config(args)
    with _open_mail_inbox(args) as client:
        folder = client.resolve_folder(provider, explicit_folder=explicit_folder)
        fetched_items = client.fetch_messages(folder, since=args.since, limit=args.limit)
    parser_config = (((config.mail.get("parsers") or {}).get(provider)) if config else None) or {}
    if args.no_provider_filter:
        filter_result = None
        source_items = fetched_items
    elif parser_config:
        parser = build_alert_parser(provider, parser_config, root=config.root)
        source_items = []
        for item in fetched_items:
            parsed = parser.parse(item)
            if parsed is not None:
                source_items.append({**item, **parsed})
        skipped_by_filter = len(fetched_items) - len(source_items)
    else:
        filter_result = filter_provider_messages(provider, fetched_items)
        source_items = filter_result.matched
    root = config.root if config else Path(getattr(args, "root", None) or ".")
    state_db = Path(args.state_db)
    if not state_db.is_absolute():
        state_db = root / state_db
    store = AutomationStateStore(state_db)
    state_result = store.upsert_source_items(provider, source_items)
    skipped = (
        0 if args.no_provider_filter else (skipped_by_filter if parser_config else filter_result.skipped)
    )
    payload = {
        "run": {
            "run_key": args.run_key
            or f"{provider}-mail-fetch-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
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
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8"
        )
    _print_json(payload)
    return 0


def cmd_parse_upwork_alerts(args: argparse.Namespace) -> int:
    source_payload = json.loads(Path(args.source_payload).read_text(encoding="utf-8"))
    payload = parse_upwork_alert_payload(source_payload, run_key=args.run_key, now=args.now)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8"
        )
    _print_json(payload)
    return 0


def _smtp_setting(name: str, default: str | None = None) -> str | None:
    return os.getenv(f"JOBTRACKER_{name}") or os.getenv(name) or default


def cmd_send_report_email(args: argparse.Namespace) -> int:
    load_env_file()
    config = _optional_app_config(args)
    root = config.root if config else Path(getattr(args, "root", None) or ".")
    body_file = Path(args.body_file)
    if not body_file.is_absolute():
        body_file = root / body_file
    body = body_file.read_text(encoding="utf-8")
    to_address = normalize_space(args.to or _smtp_setting("REPORT_EMAIL_TO"))
    if not to_address:
        raise MissingConfigurationError("recipient is required via --to or JOBTRACKER_REPORT_EMAIL_TO.")
    from_address = args.from_address or _smtp_setting("SMTP_FROM") or _smtp_setting("SMTP_USER")
    provider = slugify(args.provider)
    run_key = normalize_space(args.run_key)
    key = args.idempotency_key or sha256_text(f"{provider}\n{run_key}\n{to_address}\n{args.subject}\n{body}")
    state_db = Path(args.state_db)
    if not state_db.is_absolute():
        state_db = root / state_db
    store = AutomationStateStore(state_db)
    if not store.reserve_email(
        key, provider=provider, run_key=run_key, to_address=to_address, subject=args.subject
    ):
        _print_json(
            {
                "sent": False,
                "skipped": True,
                "reason": "email idempotency key already reserved or sent",
                "idempotency_key": key,
            }
        )
        return 0
    try:
        sender = (
            build_mail_sender(config.mail["outbox"], root=config.root)
            if config and config.mail.get("outbox")
            else SmtpMailSender(sender=from_address)
        )
        sender.send(
            OutgoingMessage(
                sender=from_address or getattr(sender, "default_sender", ""),
                recipient=to_address,
                subject=args.subject,
                body=body,
            )
        )
    except Exception as exc:
        store.mark_email_failed(key, str(exc))
        raise
    store.mark_email_sent(key)
    _print_json({"sent": True, "idempotency_key": key, "to": to_address, "subject": args.subject})
    return 0


def _optional_app_config(args: argparse.Namespace):
    root = Path(getattr(args, "root", None) or ".")
    config_path = getattr(args, "config", None)
    candidate = Path(config_path) if config_path else root / "config/jobsearch.toml"
    if not candidate.is_absolute():
        candidate = root / candidate
    if not candidate.exists():
        return None
    return load_app_config(config_path, root=root)


@contextmanager
def _open_mail_inbox(args: argparse.Namespace):
    config = _optional_app_config(args)
    inbox = (
        build_mail_inbox(config.mail["inbox"], root=config.root)
        if config and config.mail.get("inbox")
        else MailImapClient()
    )
    if hasattr(inbox, "__enter__"):
        with inbox as entered:
            yield entered
    else:
        yield inbox


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
    root = Path(getattr(args, "root", None) or ".")
    payload_dir = Path(args.payload_dir)
    if not payload_dir.is_absolute():
        payload_dir = root / payload_dir
    state_db = Path(args.state_db)
    if not state_db.is_absolute():
        state_db = root / state_db
    target_store = getattr(args, "target_store", "postgres")
    payload_paths = sorted(payload_dir.rglob("*.payload.json"))
    synced = 0
    skipped = 0
    failed: list[dict[str, str]] = []
    if not payload_paths:
        _print_json(
            {
                "payload_dir": str(payload_dir),
                "target_store": target_store,
                "synced": synced,
                "skipped": skipped,
                "failed": failed,
                "dry_run": args.dry_run,
            }
        )
        return 0
    state = AutomationStateStore(state_db)
    target_context = (
        nullcontext(None) if args.dry_run else open_job_store({"backend": target_store}, root=root)
    )
    with target_context as target:
        for payload_path in payload_paths:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            run_key = _payload_run_key(payload)
            if not run_key:
                failed.append({"payload": str(payload_path), "error": "missing run_key"})
                continue
            provider = _provider_from_payload(payload_path, payload, args.provider)
            if args.provider and provider != slugify(args.provider):
                continue
            if state.is_run_db_synced(run_key):
                skipped += 1
                continue
            if args.dry_run:
                skipped += 1
                continue
            try:
                state.mark_run_sync_attempt(provider, run_key, str(payload_path))
                target.upsert_run_payload(provider, str(payload_path))
                state.mark_run_db_synced(provider, run_key, str(payload_path))
                synced += 1
            except Exception as exc:
                state.mark_run_sync_attempt(provider, run_key, str(payload_path), error=str(exc))
                state.record_run_event(
                    provider, run_key, "db_sync_failed", str(exc), {"payload_path": str(payload_path)}
                )
                failed.append({"payload": str(payload_path), "run_key": run_key, "error": str(exc)})
    _print_json(
        {
            "payload_dir": str(payload_dir),
            "target_store": target_store,
            "synced": synced,
            "skipped": skipped,
            "failed": failed,
            "dry_run": args.dry_run,
        }
    )
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


def cmd_fetch_source(args: argparse.Namespace) -> int:
    config = load_app_config(args.config, root=Path(args.root or "."))
    source_slug = slugify(args.source)
    configured = {slugify(slug) for slug in config.source_configs}
    if source_slug not in configured and source_slug not in source_registry.all():
        available = sorted({*configured, *source_registry.all()})
        raise ValueError(f"Unknown source {args.source!r}. Available: {', '.join(available) or '(none)'}")
    now = _parse_datetime_arg(getattr(args, "now", None))
    payload_out = str(config.resolve_path(args.payload_out)) if args.payload_out else None
    if not payload_out and not args.dry_run:
        timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        payload_out = str(config.payload_dir / f"{source_slug}-{timestamp}.payload.json")
    kwargs = {
        "dry_run": args.dry_run,
        "payload_out": payload_out,
        "fixture_dir": (
            config.resolve_path(args.fixture_dir) if getattr(args, "fixture_dir", None) else None
        ),
        "targets_path": config.resolve_path(args.targets) if getattr(args, "targets", None) else None,
        "config_path": config.sources[0],
        "root": config.root,
        "now": now,
        "max_pages": getattr(args, "max_pages", 1),
        "detail_limit": getattr(args, "detail_limit", None),
    }
    if args.dry_run:
        result = collect_provider_run(source_slug, conn=None, **kwargs)
    else:
        with open_job_store(config.store, root=config.root) as store:
            result = collect_provider_run(
                source_slug,
                conn=getattr(store, "conn", None),
                store=store,
                **kwargs,
            )
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
    config = load_app_config(getattr(args, "config", None), root=Path(getattr(args, "root", None) or "."))
    fixture_dir = config.resolve_path(args.fixture_dir) if getattr(args, "fixture_dir", None) else None
    store_context = nullcontext(None) if args.no_db else open_job_store(config.store, root=config.root)
    try:
        with store_context as store:
            manifest = prepare_jobboard_run(
                profile_slug=args.profile,
                providers=providers,
                output_dir=config.resolve_path(args.output_dir),
                payload_dir=config.resolve_path(args.payload_dir),
                profile_dir=config.profile_dir,
                root=config.root,
                store=store,
                config_path=config.sources[0],
                include_db=not args.no_db,
                fixture_dir=fixture_dir,
                now=now,
                max_pages=args.max_pages,
                detail_limit=args.detail_limit,
            )
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc
    _print_json(manifest)
    return 0


# --------------------------------------------------------------------------- calendar


def _calendar_root(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "root", None) or ".")


def _calendar_path(args: argparse.Namespace, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else _calendar_root(args) / path


def _calendar_setup(args: argparse.Namespace):
    root = _calendar_root(args)
    load_env_file(root / ".env")
    config = _optional_app_config(args)
    options = dict(config.calendar) if config else {}
    settings = settings_from_options(options, os.environ)
    if getattr(args, "calendar", None):
        settings = replace(settings, calendar=args.calendar)
    return config, options, settings


def _calendar_service(args: argparse.Namespace):
    config, options, settings = _calendar_setup(args)
    if not options:
        raise MissingConfigurationError(
            "calendar is not configured: add a [calendar] table to config/jobsearch.toml "
            "(see Docs/onboarding/CALENDAR.md)"
        )
    root = config.root if config else _calendar_root(args)
    backend = build_calendar_backend(options, root=root)
    fixed = str(options.get("calendar_url") or "") if not getattr(args, "calendar", None) else ""
    cal_url = fixed or resolve_calendar_url(backend, settings.calendar)
    return CalendarService(backend, cal_url, settings), backend


def _calendar_ident(args: argparse.Namespace) -> str:
    if getattr(args, "uid", None):
        return args.uid
    if getattr(args, "key", None):
        return key_to_uid(args.key)
    raise ValueError("pass --key or --uid")


def _fetch_imap_message(args: argparse.Namespace, ref: str) -> tuple[bytes, str]:
    if ":" not in ref:
        raise ValueError("--imap expects FOLDER:UID")
    folder, uid = ref.rsplit(":", 1)
    config = _optional_app_config(args)
    inbox = dict(((config.mail.get("inbox") if config else None) or {}))
    allowed = {key: inbox[key] for key in ("host", "user") if inbox.get(key)}
    with MailImapClient(**allowed) as client:
        raw = client.fetch_raw(folder, uid)
    if not raw:
        raise ValueError(f"message {ref} not found")
    return raw, f"imap://{folder}/{uid}"


def cmd_calendar_calendars(args: argparse.Namespace) -> int:
    config, options, _ = _calendar_setup(args)
    if not options:
        raise MissingConfigurationError("calendar is not configured: add a [calendar] table")
    backend = build_calendar_backend(options, root=config.root if config else _calendar_root(args))
    items: list[CalendarInfo] = backend.calendars()
    _print_json([{"name": item.name, "url": item.url} for item in items])
    return 0


def cmd_calendar_list(args: argparse.Namespace) -> int:
    service, _ = _calendar_service(args)
    tz = service.settings.default_timezone
    now = datetime.now(timezone.utc)
    start = aware(args.date_from, None, tz) if args.date_from else now - timedelta(days=30)
    end = aware(args.date_to, None, tz) if args.date_to else now + timedelta(days=90)
    rows = service.list_events(start, end, grep=args.grep, managed_only=args.managed_only)
    if args.json:
        _print_json(rows)
        return 0
    for row in rows:
        flags = ("M" if row["managed"] else "-") + ("R" if row["recurring"] else " ")
        print(
            f"{row['start_local']}  {flags} {row['status'][:4]}  {row['title']}  [{row['key'] or row['uid']}]"
        )
    return 0


def cmd_calendar_parse(args: argparse.Namespace) -> int:
    _, _, settings = _calendar_setup(args)
    if args.ics:
        path = _calendar_path(args, args.ics)
        result = {
            "evidence": str(args.ics),
            "specs": ics_to_specs(path.read_text(encoding="utf-8"), str(args.ics), args.default_tz, settings),
        }
    else:
        if args.eml:
            raw, evidence = _calendar_path(args, args.eml).read_bytes(), str(args.eml)
        else:
            raw, evidence = _fetch_imap_message(args, args.imap)
        result = parse_message(raw, evidence, args.default_tz, settings)
    if args.out:
        out = _calendar_path(args, args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _print_json(result)
    return 0


def _load_specs(args: argparse.Namespace, settings) -> list[dict]:
    if args.ics:
        path = _calendar_path(args, args.ics)
        return ics_to_specs(path.read_text(encoding="utf-8"), args.evidence or str(args.ics), None, settings)
    if not args.spec:
        raise ValueError("pass a spec file or --ics")
    data = json.loads(_calendar_path(args, args.spec).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "specs" in data:
        return list(data["specs"])
    return list(data) if isinstance(data, list) else [data]


def cmd_calendar_apply(args: argparse.Namespace) -> int:
    service, _ = _calendar_service(args)
    specs = _load_specs(args, service.settings)
    results = [
        service.apply(spec, dry_run=args.dry_run, allow_unmanaged=args.allow_unmanaged) for spec in specs
    ]
    _print_json(results)
    return 1 if any(item.get("result") == "invalid" for item in results) else 0


def _calendar_found(args: argparse.Namespace):
    service, _ = _calendar_service(args)
    uid = _calendar_ident(args)
    return service, uid, service.find(uid)


def cmd_calendar_update(args: argparse.Namespace) -> int:
    service, uid, found = _calendar_found(args)
    if not found:
        _print_json({"result": "not_found", "uid": uid})
        return 1
    spec = service.patch(
        found,
        start=args.start,
        end=args.end,
        timezone_name=args.timezone,
        title=args.title,
        meeting_url=args.meeting_url,
        location=args.location,
        notes_append=args.notes_append,
        evidence=args.evidence,
        reconfirm=args.reconfirm,
    )
    _print_json(service.apply(spec, dry_run=args.dry_run, allow_unmanaged=args.allow_unmanaged))
    return 0


def cmd_calendar_cancel(args: argparse.Namespace) -> int:
    service, uid, found = _calendar_found(args)
    if not found:
        _print_json({"result": "not_found", "uid": uid})
        return 1
    delete = args.calendar_command == "delete" or getattr(args, "delete", False)
    if delete and not args.yes and not args.dry_run:
        raise ValueError("deleting removes the event for good: add --yes (cancel keeps it marked)")
    spec = {
        "action": "cancel",
        "key": found.event.value("X-JOBSEARCH-KEY") or uid,
        "uid": uid,
        "cancel_reason": getattr(args, "reason", None) or "",
        "source": {"type": "manual", "evidence": getattr(args, "evidence", None) or ""},
    }
    _print_json(
        service.apply(spec, dry_run=args.dry_run, allow_unmanaged=args.allow_unmanaged, delete=delete)
    )
    return 0


def cmd_calendar_export(args: argparse.Namespace) -> int:
    service, uid, found = _calendar_found(args)
    if not found:
        _print_json({"result": "not_found", "uid": uid})
        return 1
    if args.format == "ics":
        sys.stdout.write(serialize(found.cal))
    else:
        _print_json(service.spec_of(found))
    return 0


def cmd_calendar_reply(args: argparse.Namespace) -> int:
    config, _, settings = _calendar_setup(args)
    ics_text = _calendar_path(args, args.ics).read_text(encoding="utf-8")
    ics, to, subject, attendee = build_reply(ics_text, args.partstat, args.me, settings)
    out = _calendar_path(args, args.out) if args.out else None
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(ics, encoding="utf-8")
    if not args.send:
        _print_json(
            {
                "result": "built",
                "to": to,
                "subject": subject,
                "from_attendee": attendee,
                "out": str(out or ""),
            }
        )
        if not out:
            sys.stdout.write(ics)
        return 0
    if not args.confirm_send:
        raise ValueError(
            "sending a reply is a message on the user's behalf: get approval, then add --confirm-send"
        )
    outbox = dict(((config.mail.get("outbox") if config else None) or {}))
    _print_json(send_reply(ics, to, subject, attendee, outbox=outbox, env=os.environ))
    return 0


def _add_calendar_parser(subparsers) -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", help="Path to jobsearch.toml (default: config/jobsearch.toml)")
    common.add_argument("--root", help="Project root directory")
    common.add_argument("--calendar", help="Calendar name (default: [calendar].calendar)")
    calendar = subparsers.add_parser(
        "calendar", help="Keep interview events in a calendar in step with mail (CalDAV or .ics directory)"
    )
    sub = calendar.add_subparsers(dest="calendar_command", required=True)

    sub.add_parser("calendars", parents=[common], help="List calendars (read-only)").set_defaults(
        func=cmd_calendar_calendars
    )

    listing = sub.add_parser("list", parents=[common], help="List events in a window")
    listing.add_argument("--from", dest="date_from", help="Start (ISO date/time; default 30 days ago)")
    listing.add_argument("--to", dest="date_to", help="End (ISO date/time; default 90 days ahead)")
    listing.add_argument("--grep", help="Regular expression matched against title and notes")
    listing.add_argument("--managed-only", action="store_true", help="Only events written by this tool")
    listing.add_argument("--json", action="store_true", help="Print JSON rows")
    listing.set_defaults(func=cmd_calendar_list)

    parse = sub.add_parser("parse", parents=[common], help="Classify an invite or e-mail into event specs")
    source = parse.add_mutually_exclusive_group(required=True)
    source.add_argument("--ics", help="iCalendar file")
    source.add_argument("--eml", help="RFC 822 message file")
    source.add_argument("--imap", help="FOLDER:UID from the configured inbox (read-only)")
    parse.add_argument("--default-tz", help="Zone for floating times; marked as unconfirmed")
    parse.add_argument("--out", help="Write the result JSON to this file")
    parse.set_defaults(func=cmd_calendar_parse)

    apply = sub.add_parser("apply", parents=[common], help="Create/update/cancel/delete from specs")
    apply.add_argument("spec", nargs="?", help="Spec JSON: one object, a list, or `parse` output")
    apply.add_argument("--ics", help="Apply an iCalendar invite directly")
    apply.add_argument("--evidence", default="", help="Evidence reference recorded in the event")
    apply.add_argument("--dry-run", action="store_true", help="Show the result and iCalendar; write nothing")
    apply.add_argument("--allow-unmanaged", action="store_true", help="Also change events not made here")
    apply.set_defaults(func=cmd_calendar_apply)

    for name, helptext, func in (
        ("update", "Patch one managed event", cmd_calendar_update),
        ("cancel", "Mark a managed event as cancelled (kept, alarms removed)", cmd_calendar_cancel),
        ("delete", "Remove a managed event for good (needs --yes)", cmd_calendar_cancel),
        ("export", "Print the stored spec (JSON) or raw iCalendar", cmd_calendar_export),
    ):
        command = sub.add_parser(name, parents=[common], help=helptext)
        command.add_argument("--key", help="Event key, e.g. invite:<UID> or manual:<slug>")
        command.add_argument("--uid", help="Calendar object UID")
        if name != "export":
            command.add_argument("--dry-run", action="store_true", help="Show the result; write nothing")
            command.add_argument(
                "--allow-unmanaged", action="store_true", help="Also change unmanaged events"
            )
        if name == "update":
            for option in ("start", "end", "timezone", "title", "meeting-url", "location", "notes-append"):
                command.add_argument(f"--{option}")
            command.add_argument("--evidence", help="Evidence reference for the change")
            command.add_argument("--reconfirm", action="store_true", help="Clear a cancellation")
        if name == "cancel":
            command.add_argument("--reason", required=True, help="Cancellation reason")
            command.add_argument("--evidence", required=True, help="Evidence reference")
            command.add_argument("--delete", action="store_true", help="Delete instead of marking")
        if name in ("cancel", "delete"):
            command.add_argument("--yes", action="store_true", help="Confirm a permanent delete")
        if name == "export":
            command.add_argument("--format", choices=("json", "ics"), default="json")
        command.set_defaults(func=func)

    reply = sub.add_parser("reply", parents=[common], help="Build (and optionally send) an iTIP REPLY")
    reply.add_argument("--ics", required=True, help="The invite to answer")
    reply.add_argument("--partstat", choices=("ACCEPTED", "DECLINED", "TENTATIVE"), required=True)
    reply.add_argument("--as", dest="me", help="Attendee address to answer as")
    reply.add_argument("--out", help="Write the REPLY iCalendar to this file")
    reply.add_argument("--send", action="store_true", help="Send through the configured SMTP outbox")
    reply.add_argument(
        "--confirm-send", action="store_true", help="The user approved this exact reply; required with --send"
    )
    reply.set_defaults(func=cmd_calendar_reply)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobtracker", description="Local-first job search automation and tracking CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate = subparsers.add_parser("migrate", help="Apply SQL migrations")
    migrate.add_argument(
        "--dry-run", action="store_true", help="List pending migrations without applying them"
    )
    migrate.set_defaults(func=cmd_migrate)

    legacy = subparsers.add_parser(
        "import-legacy", help="Import the legacy semicolon-delimited job search CSV"
    )
    legacy.add_argument(
        "--csv", required=True, help="Path to legacy CSV, for example Docs/Tracking/Job search '25.csv"
    )
    legacy.add_argument(
        "--links-pdf",
        help="Optional PDF export containing the clickable vacancy links. Defaults to a same-name .pdf next to the CSV.",
    )
    legacy.add_argument("--dry-run", action="store_true", help="Parse and summarize without writing to DB")
    legacy.set_defaults(func=cmd_import_legacy)

    linkedin = subparsers.add_parser(
        "import-linkedin-tracking", help="Import LinkedIn jobs and application tracker CSVs"
    )
    linkedin.add_argument(
        "--jobs-csv",
        help="Path to linkedin_jobs.csv. Defaults to Docs/Tracking/linkedin_jobs.csv when present",
    )
    linkedin.add_argument(
        "--active-csv",
        help="Path to linkedin_applications_active.csv. Defaults to Docs/Tracking/linkedin_applications_active.csv when present",
    )
    linkedin.add_argument(
        "--archived-csv",
        help="Path to linkedin_applications_archived.csv. Defaults to Docs/Tracking/linkedin_applications_archived.csv when present",
    )
    linkedin.add_argument(
        "--as-of", help="Anchor date for LinkedIn relative dates like '2mo ago', in YYYY-MM-DD format"
    )
    linkedin.add_argument("--dry-run", action="store_true", help="Parse and summarize without writing to DB")
    linkedin.set_defaults(func=cmd_import_linkedin_tracking)

    greenhouse = subparsers.add_parser("import-greenhouse", help="Import Greenhouse application tracker CSV")
    greenhouse.add_argument(
        "--csv", help="Path to greenhouse.csv. Defaults to Docs/Tracking/greenhouse.csv when present"
    )
    greenhouse.add_argument(
        "--as-of", help="Anchor date for relative dates like '13 days ago', in YYYY-MM-DD format"
    )
    greenhouse.add_argument(
        "--dry-run", action="store_true", help="Parse and summarize without writing to DB"
    )
    greenhouse.set_defaults(func=cmd_import_greenhouse)

    upsert = subparsers.add_parser("upsert-run", help="Upsert one automation run payload")
    upsert.add_argument("--provider", required=True, help="Provider slug, for example linkedin or upwork")
    upsert.add_argument("--payload", required=True, help="Path to normalized automation payload JSON")
    upsert.add_argument("--report", help="Optional Markdown report path to upload/register")
    upsert.add_argument("--root", default=".", help="Project root directory")
    upsert.add_argument("--config", help="Path to jobsearch.toml")
    upsert.set_defaults(func=cmd_upsert_run)

    dupes = subparsers.add_parser(
        "check-duplicates", help="Check whether an opportunity was already seen/applied to"
    )
    dupes.add_argument("--provider", required=True)
    dupes.add_argument("--company")
    dupes.add_argument("--title")
    dupes.add_argument("--external-id")
    dupes.add_argument("--root", default=".", help="Project root directory")
    dupes.add_argument("--config", help="Path to jobsearch.toml")
    dupes.set_defaults(func=cmd_check_duplicates)

    summary = subparsers.add_parser("export-summary", help="Export a Markdown application summary")
    summary.add_argument("--application-id", required=True)
    summary.add_argument("--output")
    summary.add_argument("--root", default=".", help="Project root directory")
    summary.add_argument("--config", help="Path to jobsearch.toml")
    summary.set_defaults(func=cmd_export_summary)

    db_smoke = subparsers.add_parser("db-smoke", help="Run a read-only database connection smoke test")
    db_smoke.add_argument(
        "--test", action="store_true", help="Use SUPABASE_TEST_DB_URL instead of SUPABASE_DB_URL"
    )
    db_smoke.add_argument("--write-test", action="store_true", help="Also run a rollback-only write test")
    db_smoke.set_defaults(func=cmd_db_smoke)

    validate = subparsers.add_parser("validate-payload", help="Validate and normalize an automation payload")
    validate.add_argument("--provider", required=True, help="Provider slug, for example linkedin or upwork")
    validate.add_argument("--payload", required=True, help="Path to automation payload JSON")
    validate.add_argument("--normalized-out", help="Optional path to write the normalized payload JSON")
    validate.set_defaults(func=cmd_validate_payload)

    index = subparsers.add_parser(
        "build-local-index", help="Summarize local payload history for fallback dedupe"
    )
    index.add_argument(
        "--payload-dir",
        default="outputs/automation-payloads",
        help="Directory containing *.payload.json files",
    )
    index.add_argument("--now", help=argparse.SUPPRESS)
    index.set_defaults(func=cmd_build_local_index)

    dedupe = subparsers.add_parser(
        "dedupe-candidates", help="Enrich a payload with local duplicate/application evidence"
    )
    dedupe.add_argument("--provider", required=True)
    dedupe.add_argument("--payload", required=True)
    dedupe.add_argument(
        "--payload-dir",
        default="outputs/automation-payloads",
        help="Directory containing prior *.payload.json files",
    )
    dedupe.add_argument("--output", help="Optional path to write enriched payload JSON")
    dedupe.add_argument(
        "--include-db",
        action="store_true",
        help="Also check Supabase for existing opportunities and applications",
    )
    dedupe.add_argument("--now", help=argparse.SUPPRESS)
    dedupe.set_defaults(func=cmd_dedupe_candidates)

    folders = subparsers.add_parser(
        "discover-mail-folders", help="List IMAP folders and resolve job-alert aliases"
    )
    folders.add_argument("--root", default=".", help="Project root for config and relative paths")
    folders.add_argument("--config", help="Path to jobsearch.toml")
    folders.set_defaults(func=cmd_discover_mail_folders)

    labels = subparsers.add_parser("discover-gmail-labels", help="Alias for discover-mail-folders")
    labels.add_argument("--root", default=".", help="Project root for config and relative paths")
    labels.add_argument("--config", help="Path to jobsearch.toml")
    labels.set_defaults(func=cmd_discover_mail_folders)

    def add_mail_fetch_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--provider",
            required=True,
            help="Configured parser/provider slug whose mail folder should be fetched",
        )
        parser.add_argument("--root", default=".", help="Project root for config and relative paths")
        parser.add_argument("--config", help="Path to jobsearch.toml")
        parser.add_argument(
            "--folder",
            help="Explicit IMAP folder name. Defaults to discovered job/Provider or Job(s)/Alerts alias.",
        )
        parser.add_argument("--label", help=argparse.SUPPRESS)
        parser.add_argument("--since", help="Optional IMAP SINCE date, for example 12-May-2026")
        parser.add_argument(
            "--limit", type=int, help="Maximum newest messages to fetch before provider filtering"
        )
        parser.add_argument(
            "--no-provider-filter",
            action="store_true",
            help="Do not filter mixed-folder messages by provider sender/content",
        )
        parser.add_argument("--state-db", default="outputs/automation-state/state.sqlite")
        parser.add_argument("--run-key")
        parser.add_argument("--output", help="Optional path to write fetched source payload JSON")
        parser.set_defaults(func=cmd_fetch_mail_folder)

    fetch_mail = subparsers.add_parser(
        "fetch-mail-folder", help="Fetch provider messages from an IMAP folder into local source state"
    )
    add_mail_fetch_args(fetch_mail)

    fetch_gmail = subparsers.add_parser("fetch-gmail-label", help="Alias for fetch-mail-folder")
    add_mail_fetch_args(fetch_gmail)

    parse_upwork = subparsers.add_parser(
        "parse-upwork-alerts", help="Parse fetched Upwork alert emails into an automation payload"
    )
    parse_upwork.add_argument(
        "--source-payload", required=True, help="Payload produced by fetch-mail-folder for provider upwork"
    )
    parse_upwork.add_argument("--output", help="Optional path to write parsed automation payload JSON")
    parse_upwork.add_argument("--run-key", help="Run key for the parsed automation payload")
    parse_upwork.add_argument("--now", help=argparse.SUPPRESS)
    parse_upwork.set_defaults(func=cmd_parse_upwork_alerts)

    send_email = subparsers.add_parser(
        "send-report-email", help="Send a report email through SMTP with idempotency"
    )
    send_email.add_argument("--provider", required=True)
    send_email.add_argument("--run-key", required=True)
    send_email.add_argument("--to")
    send_email.add_argument("--from-address")
    send_email.add_argument("--subject", required=True)
    send_email.add_argument("--body-file", required=True)
    send_email.add_argument("--idempotency-key")
    send_email.add_argument("--state-db", default="outputs/automation-state/state.sqlite")
    send_email.add_argument("--root", default=".", help="Project root for config and relative paths")
    send_email.add_argument("--config", help="Path to jobsearch.toml")
    send_email.set_defaults(func=cmd_send_report_email)

    sync = subparsers.add_parser(
        "sync-pending-runs", help="Upsert local payloads that have not been marked DB-synced"
    )
    sync.add_argument(
        "--payload-dir",
        default="outputs/automation-payloads",
        help="Directory containing *.payload.json files",
    )
    sync.add_argument("--provider", help="Optional provider filter")
    sync.add_argument("--state-db", default="outputs/automation-state/state.sqlite")
    sync.add_argument("--dry-run", action="store_true")
    sync.add_argument("--keep-going", action="store_true", help="Return success even if some payloads fail")
    sync.add_argument("--target-store", choices=["postgres"], default="postgres", help="Replay target store")
    sync.add_argument("--root", default=".", help="Project root for relative paths")
    sync.set_defaults(func=cmd_sync_pending_runs)

    def add_fetch_common(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run", action="store_true", help="Fetch and summarize without writing to DB"
        )
        parser.add_argument("--payload-out", help="Optional path for the normalized payload JSON")
        parser.add_argument(
            "--max-pages", type=int, default=1, help="Maximum listing pages to fetch where applicable"
        )
        parser.add_argument(
            "--detail-limit", type=int, help="Maximum number of unseen jobs to enrich with detail fetches"
        )
        parser.add_argument(
            "--targets",
            help="Optional provider target TOML path. Defaults to profile/provider_targets.toml or jobtracker/fixtures/provider_targets.toml",
        )
        parser.add_argument("--fixture-dir", help=argparse.SUPPRESS)
        parser.add_argument("--now", help=argparse.SUPPRESS)

    fetch_source = subparsers.add_parser("fetch-source", help="Fetch any configured or plugin source by slug")
    fetch_source.add_argument("source", help="Source slug from [sources.<slug>] or plugins")
    fetch_source.add_argument("--root", default=".", help="Project root directory")
    fetch_source.add_argument("--config", help="Path to jobsearch.toml")
    add_fetch_common(fetch_source)
    fetch_source.set_defaults(func=cmd_fetch_source)

    fetch_dou = subparsers.add_parser("fetch-dou", help="Compatibility alias for fetching DOU")
    add_fetch_common(fetch_dou)
    fetch_dou.set_defaults(func=cmd_fetch_dou)

    fetch_workua = subparsers.add_parser("fetch-workua", help="Compatibility alias for fetching Work.ua")
    add_fetch_common(fetch_workua)
    fetch_workua.set_defaults(func=cmd_fetch_workua)

    fetch_djinni = subparsers.add_parser("fetch-djinni", help="Compatibility alias for fetching Djinni")
    add_fetch_common(fetch_djinni)
    fetch_djinni.set_defaults(func=cmd_fetch_djinni)

    fetch_greenhouse = subparsers.add_parser(
        "fetch-greenhouse-jobs", help="Compatibility alias for fetching Greenhouse boards"
    )
    fetch_greenhouse.add_argument(
        "--dry-run", action="store_true", help="Fetch and summarize without writing to DB"
    )
    fetch_greenhouse.add_argument("--payload-out", help="Optional path for the normalized payload JSON")
    fetch_greenhouse.add_argument(
        "--board-token", action="append", help="Explicit Greenhouse board token to query. May be repeated."
    )
    fetch_greenhouse.add_argument("--max-boards", type=int, help="Maximum number of boards to query")
    fetch_greenhouse.add_argument("--fixture-dir", help=argparse.SUPPRESS)
    fetch_greenhouse.add_argument("--now", help=argparse.SUPPRESS)
    fetch_greenhouse.set_defaults(func=cmd_fetch_greenhouse_jobs)

    benchmark = subparsers.add_parser(
        "benchmark-sources", help="Benchmark discovery collectors in fixture mode or live mode"
    )
    benchmark.add_argument(
        "--providers",
        required=True,
        help="Comma-separated provider slugs, for example dou,workua,djinni,greenhouse",
    )
    benchmark.add_argument(
        "--live", action="store_true", help="Use live network fetches instead of bundled fixtures"
    )
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
    prepare_jobboards.add_argument("--profile", required=True, help="Configured profile slug to run")
    prepare_jobboards.add_argument(
        "--providers", required=True, help="Comma-separated configured providers to fetch"
    )
    prepare_jobboards.add_argument(
        "--output-dir",
        default="outputs/automation-payloads",
        help="Directory for manifest and payload artifacts",
    )
    prepare_jobboards.add_argument(
        "--payload-dir",
        default="outputs/automation-payloads",
        help="Directory used for local fallback dedupe history",
    )
    prepare_jobboards.add_argument(
        "--max-pages", type=int, default=1, help="Maximum listing pages to fetch where applicable"
    )
    prepare_jobboards.add_argument(
        "--detail-limit", type=int, help="Override provider default detail enrichment limit"
    )
    prepare_jobboards.add_argument(
        "--no-db",
        action="store_true",
        help="Skip configured-store duplicate checks and use only the local fallback index",
    )
    prepare_jobboards.add_argument("--root", default=".", help="Project root for config and relative paths")
    prepare_jobboards.add_argument("--config", help="Path to jobsearch.toml")
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
    doctor.add_argument(
        "--skip-network", action="store_true", help="Skip DB/IMAP/SMTP and connector network checks"
    )
    doctor.set_defaults(func=cmd_doctor)

    run_cmd = subparsers.add_parser(
        "run", help="Execute a configured pipeline (source -> dedupe -> store -> notify)"
    )
    run_cmd.add_argument("pipeline", help="Pipeline name from config/jobsearch.toml")
    run_cmd.add_argument("--config", help="Path to jobsearch.toml (default: config/jobsearch.toml)")
    run_cmd.add_argument("--root", help="Project root directory")
    run_cmd.add_argument(
        "--dry-run", action="store_true", help="Fetch and dedupe without DB store or notifications"
    )
    run_cmd.add_argument("--fixture-dir", help=argparse.SUPPRESS)
    run_cmd.add_argument("--now", help=argparse.SUPPRESS)
    run_cmd.set_defaults(func=cmd_run)

    _add_calendar_parser(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (
        MissingConfigurationError,
        MissingDependencyError,
        FileNotFoundError,
        ValueError,
        RuntimeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
