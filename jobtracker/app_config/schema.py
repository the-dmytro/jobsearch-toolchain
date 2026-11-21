from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Any

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")


class ConfigValidationError(ValueError):
    pass


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigValidationError(f"{path} must be a table")
    return value


def _require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigValidationError(f"{path} must be a non-empty string")
    return value.strip()


def _require_str_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ConfigValidationError(f"{path} must be a non-empty array")
    result = [str(item).strip() for item in value if str(item).strip()]
    if not result:
        raise ConfigValidationError(f"{path} must contain at least one value")
    return result


def validate_jobsearch_config(data: dict[str, Any]) -> dict[str, Any]:
    root = _require_mapping(data, "config")
    schema_version = root.get("schema_version", 1)
    if schema_version != 1:
        raise ConfigValidationError("schema_version must be 1")
    paths = _require_mapping(root.get("paths", {}), "paths")
    validated_paths = {
        "config_dir": str(paths.get("config_dir") or "config"),
        "profile_dir": str(paths.get("profile_dir") or "profile"),
        "output_dir": str(paths.get("output_dir") or "outputs/automation-payloads"),
        "payload_dir": str(paths.get("payload_dir") or "outputs/automation-payloads"),
    }

    pipelines_raw = _require_mapping(root.get("pipelines", {}), "pipelines")
    pipelines: dict[str, dict[str, Any]] = {}
    for name, pipeline in pipelines_raw.items():
        pipeline_table = _require_mapping(pipeline, f"pipelines.{name}")
        pipeline_type = _require_str(pipeline_table.get("type"), f"pipelines.{name}.type")
        if pipeline_type not in {"jobboard"}:
            raise ConfigValidationError(f"pipelines.{name}.type must be one of: jobboard")
        profile = _require_str(pipeline_table.get("profile"), f"pipelines.{name}.profile")
        providers = pipeline_table.get("providers")
        provider_list = _require_str_list(providers, f"pipelines.{name}.providers")
        notify = pipeline_table.get("notify") or {}
        notify_table = _require_mapping(notify, f"pipelines.{name}.notify") if notify else {}
        channels = notify_table.get("channels") or []
        if channels and not isinstance(channels, list):
            raise ConfigValidationError(f"pipelines.{name}.notify.channels must be an array")
        pipelines[name] = {
            "type": pipeline_type,
            "profile": profile,
            "providers": provider_list,
            "output_dir": str(pipeline_table.get("output_dir") or validated_paths["output_dir"]),
            "payload_dir": str(pipeline_table.get("payload_dir") or validated_paths["payload_dir"]),
            "include_db": bool(pipeline_table.get("include_db", True)),
            "max_pages": int(pipeline_table.get("max_pages") or 1),
            "detail_limit": pipeline_table.get("detail_limit"),
            "notify_channels": [str(item).strip().lower() for item in channels if str(item).strip()],
        }

    notify_raw = _require_mapping(root.get("notify", {}), "notify")
    notify: dict[str, dict[str, Any]] = {}
    for channel, channel_config in notify_raw.items():
        notify[str(channel).strip().lower()] = _require_mapping(channel_config, f"notify.{channel}")

    store_raw = _require_mapping(root.get("store", {}), "store")
    backend = _require_str(store_raw.get("backend", "sqlite"), "store.backend").lower()
    store = dict(store_raw)
    store.update(
        {
            "backend": backend,
            "sqlite_path": str(store_raw.get("sqlite_path") or "outputs/jobsearch.sqlite3"),
            "artifact_backend": _require_str(
                store_raw.get("artifact_backend", "local"), "store.artifact_backend"
            ).lower(),
            "artifact_local_path": str(store_raw.get("artifact_local_path") or "outputs/artifacts"),
        }
    )

    sources_raw = _require_mapping(root.get("sources", {}), "sources")
    sources = {
        str(slug).strip().lower(): dict(_require_mapping(value, f"sources.{slug}"))
        for slug, value in sources_raw.items()
    }
    for slug, source in sources.items():
        source["kind"] = _require_str(source.get("kind"), f"sources.{slug}.kind").lower()

    mail_raw = _require_mapping(root.get("mail", {}), "mail")
    mail = dict(mail_raw)

    calendar = dict(_require_mapping(root.get("calendar", {}), "calendar"))
    if calendar:
        calendar["kind"] = _require_str(calendar.get("kind", "caldav"), "calendar.kind").lower()
        for name in ("calendar", "url", "calendar_url", "default_timezone", "path"):
            if name in calendar:
                _require_str(calendar[name], f"calendar.{name}")
        alarms = calendar.get("alarms_minutes", [])
        if not isinstance(alarms, list) or not all(
            isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in alarms
        ):
            raise ConfigValidationError("calendar.alarms_minutes must be an array of non-negative integers")
        for secret in ("password", "user", "token"):
            if secret in calendar:
                raise ConfigValidationError(
                    f"calendar.{secret} must not be stored in TOML; use {secret}_env and .env"
                )

    return {
        "schema_version": 1,
        "paths": validated_paths,
        "store": store,
        "sources": sources,
        "mail": mail,
        "calendar": calendar,
        "pipelines": pipelines,
        "notify": notify,
    }


def validate_profile_config(data: dict[str, Any], *, source_path: Path | None = None) -> dict[str, Any]:
    prefix = f"{source_path}: " if source_path else ""
    if "schema_version" not in data:
        warnings.warn(
            f"{prefix}profile config without schema_version is deprecated; add schema_version = 1 before v0.3",
            DeprecationWarning,
            stacklevel=2,
        )
    elif data["schema_version"] != 1:
        raise ConfigValidationError(f"{prefix}schema_version must be 1")
    profile = _require_mapping(data.get("profile", data), f"{prefix}profile")
    slug = _require_str(profile.get("slug"), f"{prefix}profile.slug")
    name = _require_str(profile.get("name"), f"{prefix}profile.name")
    output_slug = _require_str(profile.get("output_slug"), f"{prefix}profile.output_slug")
    targets_path = _require_str(profile.get("targets_path"), f"{prefix}profile.targets_path")
    report_path_template = _require_str(
        profile.get("report_path_template"), f"{prefix}profile.report_path_template"
    )
    email_body_template = _require_str(
        profile.get("email_body_template"), f"{prefix}profile.email_body_template"
    )
    email_subject_prefix = _require_str(
        profile.get("email_subject_prefix"), f"{prefix}profile.email_subject_prefix"
    )
    profile_files = profile.get("profile_files") or []
    evaluation_notes = profile.get("evaluation_notes") or []
    if not isinstance(profile_files, list):
        raise ConfigValidationError(f"{prefix}profile.profile_files must be an array")
    if not isinstance(evaluation_notes, list):
        raise ConfigValidationError(f"{prefix}profile.evaluation_notes must be an array")
    return {
        "slug": slug,
        "name": name,
        "output_slug": output_slug,
        "targets_path": targets_path,
        "report_path_template": report_path_template,
        "email_body_template": email_body_template,
        "email_subject_prefix": email_subject_prefix,
        "profile_files": [str(item) for item in profile_files],
        "evaluation_notes": [str(item) for item in evaluation_notes],
        "email_to": str(profile.get("email_to") or "").strip() or None,
    }


def find_placeholders(text: str) -> list[str]:
    return PLACEHOLDER_RE.findall(text)


def scan_profile_placeholders(profile_files: list[str], *, root: Path | None = None) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    base = root or Path.cwd()
    for relative_path in profile_files:
        path = Path(relative_path)
        if not path.is_absolute():
            path = base / path
        if not path.exists():
            issues.append({"path": str(path), "issue": "profile file does not exist"})
            continue
        content = path.read_text(encoding="utf-8")
        placeholders = find_placeholders(content)
        if placeholders:
            issues.append(
                {
                    "path": str(path),
                    "issue": f"unresolved placeholders: {', '.join(sorted(set(placeholders)))}",
                }
            )
    return issues
