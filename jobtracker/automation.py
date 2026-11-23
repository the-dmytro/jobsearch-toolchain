from __future__ import annotations

import os
import shutil
from contextlib import ExitStack, nullcontext
from datetime import datetime
from pathlib import Path
from typing import Any

from .app_config.loader import EXAMPLE_CONFIG_PATH, AppConfig, load_app_config
from .app_config.profiles import JobboardProfile, load_profile
from .app_config.schema import ConfigValidationError, scan_profile_placeholders
from .config import load_settings
from .core.models import CollectionContext, FetchMetrics
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


CONFIG_TEMPLATES = {
    "local": EXAMPLE_CONFIG_PATH,
    "shared": Path("config/jobsearch.shared.example.toml"),
}


def scaffold_environment(
    *, root: Path, environment: str, connector: str, hosting: str | None = None, force: bool = False
) -> str:
    """Write config/environments/<environment>.toml selecting exactly one connector."""
    from .store.connectors import get_connector

    info = get_connector(connector).info
    if hosting and info.hosting not in {"any", hosting}:
        raise ValueError(f"connector {connector!r} works only with {info.hosting!r} hosting, not {hosting!r}")
    if not environment.replace("-", "").replace("_", "").isalnum():
        raise ValueError(f"environment must be a simple name, got {environment!r}")
    path = root / "config" / "environments" / f"{environment}.toml"
    if path.exists() and not force:
        raise FileExistsError(f"{path} exists; pass --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    needs = ", ".join(info.settings)
    path.write_text(
        f"# Environment {environment!r}: select it with JOBTRACKER_ENVIRONMENT={environment}.\n"
        f'# {info.description}\n# Needs: {needs}\n[store]\nconnector = "{info.name}"\n',
        encoding="utf-8",
    )
    return str(path)


def scaffold_config(
    *, root: Path | None = None, force: bool = False, template: str = "local"
) -> dict[str, Any]:
    project_root = root or Path.cwd()
    config_dir = project_root / "config"
    profile_dir = project_root / "profile"
    config_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    skipped: list[str] = []
    if template not in CONFIG_TEMPLATES:
        raise ValueError(f"Unknown config template {template!r}. Use one of: {', '.join(CONFIG_TEMPLATES)}")
    example = project_root / CONFIG_TEMPLATES[template]
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


def check_db_connectivity(store_options: dict[str, Any]) -> list[str]:
    """Check the one database connector named in config."""
    from .store.registry import connect_postgres, postgres_connector

    try:
        connector = postgres_connector(store_options)
        missing = [name for name in connector.info.settings if not (os.getenv(name) or "").strip()]
        if connector.info.name == "postgres_direct" and not missing and not load_settings().db_url:
            missing = ["JOBTRACKER_DATABASE_URL"]
        if missing:
            return [f"database: {connector.info.name} needs {', '.join(missing)}"]
        with connect_postgres(store_options) as conn:
            with conn.cursor() as cur:
                cur.execute("select 1 as ok")
                cur.fetchone()
                cur.execute("select count(*) as applied from jobtracker_schema_migrations")
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

    from .automation_state import AutomationStateStore
    from .portability import state_db_path
    from .store.registry import describe_store

    report["checks"]["store"] = describe_store(config.store, root=config.root)
    state_db = state_db_path(config.root)
    pending = AutomationStateStore(state_db).pending_runs() if state_db.exists() else []
    report["checks"]["pending_sync"] = [
        {"run_key": row["run_key"], "payload_path": row["payload_path"], "last_error": row["last_error"]}
        for row in pending
    ]
    if pending:
        report["issues"].append(
            f"pending_sync: {len(pending)} local run(s) failed to replay; rerun sync-pending-runs"
        )

    if not skip_network:
        report["checks"]["connectors"] = check_connector_health(config)
        if config.store["backend"] == "postgres":
            report["checks"]["database"] = check_db_connectivity(config.store)
        if config.mail.get("inbox"):
            report["checks"]["imap"] = check_imap_connectivity(config.mail["inbox"], root=config.root)
        if config.mail.get("outbox"):
            report["checks"]["smtp"] = check_smtp_connectivity(config.mail["outbox"], root=config.root)
        if config.notify:
            report["checks"]["notifiers"] = check_notifier_health(config)
        for section, issues in report["checks"].items():
            if section in {"profile_placeholders", "store", "pending_sync"}:
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
    from .portability import prune_after_run
    from .store.registry import describe_store

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
    receipt = describe_store(config.store, root=config.root)
    persistence = "dry_run" if dry_run else ("skipped" if not pipeline["include_db"] else "stored")
    pruned: dict[str, Any] | None = None
    with ExitStack() as stack:
        store = None
        if not dry_run and pipeline["include_db"]:
            store = stack.enter_context(open_job_store(config.store, root=config.root))
        if store is not None:
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
                verify = getattr(store, "verify_run", None)
                if verify and not verify(result.run_key):
                    raise RuntimeError(f"Readback failed: run {result.run_key} is not in the store")
                stored.append(
                    {"provider": provider_run["provider"], **vars(result), "verified": bool(verify)}
                )
            pruned = prune_after_run(config, store, manifest)
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

    result: dict[str, Any] = {
        "pipeline": pipeline_key,
        "dry_run": dry_run,
        "persistence": persistence,
        "store": receipt,
        "manifest": manifest,
        "stored": stored,
        "notifications": notifications,
    }
    if pruned is not None:
        result["pruned"] = pruned
    return result
