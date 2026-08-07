from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .app_config.loader import EXAMPLE_CONFIG_PATH, AppConfig, load_app_config
from .app_config.profiles import JobboardProfile, load_profile
from .app_config.schema import ConfigValidationError, scan_profile_placeholders
from .config import load_settings
from .core.models import CollectionContext, FetchMetrics
from .db import connect
from .jobboard_run import prepare_jobboard_run
from .mail.generic.imap import MailImapClient
from .mail.generic.smtp import SmtpMailSender
from .notify.base import RunReport
from .notify.registry import build_notifier, notify_all
from .payloads import upsert_run_payload
from .sources.registry import source_registry
from .sources.shared.fetch import LiveFetcher
from .utils import normalize_space

PROFILE_TEMPLATE_DIR = Path("profile/templates")


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
        banks_example = templates_dir / "project-bank.example.md"
        banks_dir = profile_dir / "project-banks"
        if banks_example.exists():
            banks_dir.mkdir(parents=True, exist_ok=True)
            bank_dest = banks_dir / "example.md"
            if bank_dest.exists() and not force:
                skipped.append(str(bank_dest))
            else:
                shutil.copyfile(banks_example, bank_dest)
                created.append(str(bank_dest))
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
    fetcher = LiveFetcher(FetchMetrics())
    try:
        for slug, source in sorted(source_registry.all().items()):
            ctx = CollectionContext(
                conn=None,
                fetcher=fetcher,
                targets={},
                metrics=FetchMetrics(),
                provider_slug=slug,
                options={},
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


def check_imap_connectivity() -> list[str]:
    try:
        with MailImapClient() as client:
            folders = client.list_folders()
        if not folders:
            return ["imap: connected but no folders returned"]
    except Exception as exc:
        return [f"imap: {exc}"]
    return []


def check_smtp_connectivity() -> list[str]:
    try:
        SmtpMailSender()
    except Exception as exc:
        return [f"smtp: {exc}"]
    return []


def check_notifier_health(config: AppConfig) -> dict[str, list[str]]:
    results: dict[str, list[str]] = {}
    for channel, channel_config in config.notify.items():
        try:
            notifier = build_notifier(channel, channel_config)
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
    report: dict[str, Any] = {"ok": True, "issues": [], "checks": {}}
    try:
        config = load_app_config(config_path, root=project_root)
    except (ConfigValidationError, FileNotFoundError) as exc:
        report["ok"] = False
        report["issues"].append(str(exc))
        return report

    schema_issues = validate_config(config)
    report["checks"]["schema"] = schema_issues
    if schema_issues:
        report["ok"] = False
        report["issues"].extend(schema_issues)

    placeholder_issues: list[dict[str, str]] = []
    for profile in _iter_config_profiles(config):
        placeholder_issues.extend(scan_profile_placeholders(list(profile.profile_files), root=project_root))
    report["checks"]["profile_placeholders"] = placeholder_issues
    if placeholder_issues:
        report["ok"] = False
        report["issues"].extend(item["issue"] for item in placeholder_issues)

    if not skip_network:
        report["checks"]["connectors"] = check_connector_health(config)
        report["checks"]["database"] = check_db_connectivity()
        report["checks"]["imap"] = check_imap_connectivity()
        report["checks"]["smtp"] = check_smtp_connectivity()
        report["checks"]["notifiers"] = check_notifier_health(config)
        for section, issues in report["checks"].items():
            if section == "profile_placeholders":
                continue
            if isinstance(issues, dict):
                for name, entries in issues.items():
                    if entries:
                        report["ok"] = False
                        report["issues"].extend(f"{section}.{name}: {entry}" for entry in entries)
            elif issues:
                report["ok"] = False
                report["issues"].extend(f"{section}: {entry}" for entry in issues)
    return report


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
    manifest = prepare_jobboard_run(
        profile_slug=profile.slug,
        providers=pipeline["providers"],
        output_dir=pipeline["output_dir"],
        payload_dir=pipeline["payload_dir"],
        include_db=pipeline["include_db"] and not dry_run,
        fixture_dir=fixture_dir,
        now=now,
        max_pages=int(pipeline["max_pages"]),
        detail_limit=pipeline.get("detail_limit"),
    )

    stored: list[dict[str, Any]] = []
    if not dry_run and pipeline["include_db"]:
        with connect() as conn:
            for provider_run in manifest.get("provider_runs") or []:
                payload_path = provider_run.get("deduped_payload_path")
                if not payload_path:
                    continue
                result = upsert_run_payload(conn, provider_run["provider"], payload_path)
                stored.append({"provider": provider_run["provider"], **result})

    notifications: list[dict[str, Any]] = []
    channels = pipeline.get("notify_channels") or []
    if channels and not dry_run:
        notifiers = [build_notifier(channel, config.notify[channel]) for channel in channels]
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
