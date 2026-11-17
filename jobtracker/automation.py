from __future__ import annotations

import os
import re
import shutil
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from typing import Any

from .app_config.loader import EXAMPLE_CONFIG_PATH, AppConfig, load_app_config
from .app_config.profiles import JobboardProfile, load_profile
from .app_config.schema import ConfigValidationError, scan_profile_placeholders
from .calendar.events import settings_from_options
from .calendar.registry import build_calendar_backend
from .config import load_settings
from .core.models import CollectionContext, FetchMetrics
from .db import connect
from .jobboard_run import prepare_jobboard_run
from .mail.generic.imap import MailImapClient
from .mail.generic.smtp import SmtpMailSender
from .mail.registry import build_mail_inbox, build_mail_sender
from .notify.base import RunReport
from .notify.registry import build_notifier, notify_all
from .sources.registry import resolve_source
from .sources.shared.fetch import LiveFetcher
from .store.registry import open_job_store
from .utils import normalize_space

PROFILE_TEMPLATE_DIR = Path("profile/templates/generic")


def scaffold_config(*, root: Path | None = None, force: bool = False) -> dict[str, Any]:
    project_root = root or Path.cwd()
    config_dir = project_root / "config"
    profile_dir = project_root / "profile"
    config_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    skipped: list[str] = []
    example = project_root / EXAMPLE_CONFIG_PATH
    target = config_dir / "jobsearch.toml"
    if target.exists() and not force:
        skipped.append(str(target))
    else:
        if not example.exists():
            raise FileNotFoundError(f"Missing example config: {example}")
        shutil.copyfile(example, target)
        created.append(str(target))

    templates_dir = project_root / PROFILE_TEMPLATE_DIR
    if templates_dir.exists():
        for pattern in ("*.toml", "*.md"):
            for template_path in sorted(templates_dir.glob(pattern)):
                destination = profile_dir / template_path.name
                if destination.exists() and not force:
                    skipped.append(str(destination))
                    continue
                shutil.copyfile(template_path, destination)
                created.append(str(destination))
    return {"created": created, "skipped": skipped}


def validate_config(config: AppConfig) -> list[str]:
    issues: list[str] = []
    for pipeline_name, pipeline in config.pipelines.items():
        try:
            load_profile(pipeline["profile"], profile_dir=config.profile_dir)
        except ConfigValidationError as exc:
            issues.append(f"pipeline {pipeline_name}: {exc}")
        for channel in pipeline.get("notify_channels") or []:
            if channel not in config.notify:
                issues.append(f"pipeline {pipeline_name}: notify channel {channel!r} is not configured")
    return issues


def check_connector_health(config: AppConfig) -> dict[str, list[str]]:
    results: dict[str, list[str]] = {}
    configured = {
        normalize_space(provider).lower()
        for pipeline in config.pipelines.values()
        for provider in pipeline.get("providers") or []
    }
    configured.update(config.source_configs)
    fetcher = LiveFetcher(FetchMetrics())
    try:
        for slug in sorted(configured):
            source_config = config.source_configs.get(slug) or {}
            source = resolve_source(slug, source_config=source_config, root=config.root)
            ctx = CollectionContext(
                conn=None,
                fetcher=fetcher,
                targets={},
                metrics=FetchMetrics(),
                provider_slug=slug,
                options=dict(source_config),
            )
            try:
                results[slug] = list(source.health(ctx))
            except Exception as exc:
                results[slug] = [str(exc)]
    finally:
        fetcher.close()
    return results


def check_db_connectivity() -> list[str]:
    settings = load_settings()
    if not settings.db_url:
        return ["database: JOBTRACKER_DATABASE_URL is not configured"]
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
                cur.fetchone()
    except Exception as exc:
        return [f"database: {exc}"]
    return []


def check_imap_connectivity(options: dict[str, Any] | None = None, *, root: Path | None = None) -> list[str]:
    try:
        inbox = build_mail_inbox(options, root=root or Path.cwd()) if options else MailImapClient()
        inbox_context = inbox if hasattr(inbox, "__enter__") else nullcontext(inbox)
        with inbox_context as client:
            folders = client.list_folders()
        if not folders:
            return ["imap: connected but no folders returned"]
    except Exception as exc:
        return [f"imap: {exc}"]
    return []


def check_smtp_connectivity(options: dict[str, Any] | None = None, *, root: Path | None = None) -> list[str]:
    try:
        build_mail_sender(options, root=root or Path.cwd()) if options else SmtpMailSender()
    except Exception as exc:
        return [f"smtp: {exc}"]
    return []


def check_notifier_health(config: AppConfig) -> dict[str, list[str]]:
    results: dict[str, list[str]] = {}
    for channel, channel_config in config.notify.items():
        try:
            notifier = build_notifier(channel, channel_config, root=config.root)
            results[channel] = list(notifier.health())
        except Exception as exc:
            results[channel] = [str(exc)]
    return results


def run_doctor(
    *,
    config_path: str | Path | None = None,
    root: Path | None = None,
    skip_network: bool = False,
) -> dict[str, Any]:
    project_root = root or Path.cwd()
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "ready",
        "ok": True,
        "issues": [],
        "checks": {},
    }
    try:
        config = load_app_config(config_path, root=project_root)
    except (ConfigValidationError, FileNotFoundError) as exc:
        report["ok"] = False
        report["status"] = "error"
        report["issues"].append(str(exc))
        return report

    schema_issues = validate_config(config)
    report["checks"]["schema"] = schema_issues
    if schema_issues:
        report["ok"] = False
        report["issues"].extend(schema_issues)

    placeholder_issues: list[dict[str, str]] = []
    try:
        profiles = _iter_config_profiles(config)
    except ConfigValidationError:
        profiles = []
    for profile in profiles:
        placeholder_issues.extend(scan_profile_placeholders(list(profile.profile_files), root=project_root))
    report["checks"]["profile_placeholders"] = placeholder_issues
    if placeholder_issues:
        report["ok"] = False
        report["issues"].extend(item["issue"] for item in placeholder_issues)

    if config.calendar:
        report["checks"]["calendar"] = check_calendar_config(config, skip_network=skip_network)
        if report["checks"]["calendar"]:
            report["ok"] = False
            report["issues"].extend(f"calendar: {entry}" for entry in report["checks"]["calendar"])

    if not skip_network:
        report["checks"]["connectors"] = check_connector_health(config)
        if config.store["backend"] in {"postgres", "postgresql", "supabase"}:
            report["checks"]["database"] = check_db_connectivity()
        if config.mail.get("inbox"):
            report["checks"]["imap"] = check_imap_connectivity(config.mail["inbox"], root=config.root)
        if config.mail.get("outbox"):
            report["checks"]["smtp"] = check_smtp_connectivity(config.mail["outbox"], root=config.root)
        if config.notify:
            report["checks"]["notifiers"] = check_notifier_health(config)
        for section, issues in report["checks"].items():
            if section in ("profile_placeholders", "calendar"):
                continue
            if isinstance(issues, dict):
                for name, entries in issues.items():
                    if entries:
                        report["ok"] = False
                        report["issues"].extend(f"{section}.{name}: {entry}" for entry in entries)
            elif issues:
                report["ok"] = False
                report["issues"].extend(f"{section}: {entry}" for entry in issues)
    if report["issues"]:
        report["ok"] = False
        report["status"] = "action_required"
    return report


def check_calendar_config(config: AppConfig, *, skip_network: bool = False) -> list[str]:
    """Validate the optional [calendar] section; with network, also ask the backend for health."""
    try:
        settings_from_options(config.calendar, os.environ)
        backend = build_calendar_backend(config.calendar, root=config.root)
    except (ValueError, RuntimeError, LookupError, re.error) as exc:
        return [str(exc)]
    if skip_network:
        return []
    try:
        return list(backend.health())
    except Exception as exc:  # pragma: no cover - plugin backends
        return [f"health check failed: {type(exc).__name__}"]


def _iter_config_profiles(config: AppConfig) -> list[JobboardProfile]:
    profiles: list[JobboardProfile] = []
    seen: set[str] = set()
    for pipeline in config.pipelines.values():
        slug = normalize_space(pipeline["profile"]).lower()
        if slug in seen:
            continue
        seen.add(slug)
        profiles.append(load_profile(slug, profile_dir=config.profile_dir))
    return profiles


def run_pipeline(
    pipeline_name: str,
    *,
    config_path: str | Path | None = None,
    root: Path | None = None,
    fixture_dir: str | Path | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    project_root = root or Path.cwd()
    config = load_app_config(config_path, root=project_root)
    pipeline_key = normalize_space(pipeline_name).lower()
    if pipeline_key not in config.pipelines:
        available = ", ".join(sorted(config.pipelines)) or "(none)"
        raise ValueError(f"Unknown pipeline {pipeline_name!r}. Available: {available}")
    pipeline = config.pipelines[pipeline_key]
    if pipeline["type"] != "jobboard":
        raise ValueError(f"Unsupported pipeline type: {pipeline['type']}")

    profile = load_profile(pipeline["profile"], profile_dir=config.profile_dir)
    output_dir = config.resolve_path(pipeline["output_dir"])
    payload_dir = config.resolve_path(pipeline["payload_dir"])
    resolved_fixture_dir = config.resolve_path(fixture_dir) if fixture_dir else None

    stored: list[dict[str, Any]] = []
    if not dry_run and pipeline["include_db"]:
        with open_job_store(config.store, root=config.root) as store:
            manifest = prepare_jobboard_run(
                profile_slug=profile.slug,
                providers=pipeline["providers"],
                output_dir=output_dir,
                payload_dir=payload_dir,
                profile_dir=config.profile_dir,
                root=config.root,
                store=store,
                config_path=config.sources[0],
                include_db=True,
                fixture_dir=resolved_fixture_dir,
                now=now,
                max_pages=int(pipeline["max_pages"]),
                detail_limit=pipeline.get("detail_limit"),
            )
            for provider_run in manifest.get("provider_runs") or []:
                payload_path = provider_run.get("deduped_payload_path")
                if not payload_path:
                    continue
                result = store.upsert_run_payload(provider_run["provider"], payload_path)
                stored.append({"provider": provider_run["provider"], **vars(result)})
    else:
        manifest = prepare_jobboard_run(
            profile_slug=profile.slug,
            providers=pipeline["providers"],
            output_dir=output_dir,
            payload_dir=payload_dir,
            profile_dir=config.profile_dir,
            root=config.root,
            include_db=False,
            config_path=config.sources[0],
            fixture_dir=resolved_fixture_dir,
            now=now,
            max_pages=int(pipeline["max_pages"]),
            detail_limit=pipeline.get("detail_limit"),
        )

    notifications: list[dict[str, Any]] = []
    channels = pipeline.get("notify_channels") or []
    if channels and not dry_run:
        notifiers = [
            build_notifier(channel, config.notify[channel], root=config.root) for channel in channels
        ]
        report = RunReport(
            pipeline=pipeline_key,
            run_key=str(manifest["run"]["run_key"]),
            status=str(manifest["run"]["status"]),
            summary=str(manifest["run"]["summary"]),
            subject=profile.email_subject_prefix,
            body=str(manifest["run"]["summary"]),
            metadata={"manifest_path": manifest.get("manifest_path"), "stored": stored},
        )
        notifications = notify_all(notifiers, report)

    return {
        "pipeline": pipeline_key,
        "dry_run": dry_run,
        "manifest": manifest,
        "stored": stored,
        "notifications": notifications,
    }
