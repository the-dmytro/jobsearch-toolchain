from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAIL_FOLDER_ALIASES: dict[str, list[str]] = {
    "upwork": ["Upwork", "upwork", "job/Upwork", "Job/Upwork", "Jobs/Alerts/Upwork", "Job/Alerts/Upwork"],
    "linkedin": ["job/LinkedIn", "Job/LinkedIn", "Jobs/Alerts/LinkedIn", "Job/Alerts/LinkedIn"],
    "job-responses": ["Job", "job", "Jobs", "jobs"],
}


@dataclass(frozen=True)
class Settings:
    db_url: str | None
    test_db_url: str | None
    supabase_url: str | None
    secret_key: str | None
    service_role_key: str | None
    storage_bucket: str
    store_backend: str
    artifact_backend: str
    mail_folder_aliases: dict[str, list[str]]
    own_report_senders: frozenset[str]
    s3_artifact_bucket: str | None
    s3_artifact_prefix: str | None


def load_env_file(path: Path = Path(".env")) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    if load_dotenv:
        load_dotenv(path)
    else:
        _load_dotenv_fallback(path)


def _resolve_db_url() -> str | None:
    jobtracker_url = os.getenv("JOBTRACKER_DATABASE_URL")
    if jobtracker_url:
        return jobtracker_url
    legacy_url = os.getenv("SUPABASE_DB_URL")
    if legacy_url:
        warnings.warn(
            "SUPABASE_DB_URL is deprecated; use JOBTRACKER_DATABASE_URL instead.",
            DeprecationWarning,
            stacklevel=2,
        )
    return legacy_url


def _load_mail_folder_aliases() -> dict[str, list[str]]:
    raw = os.getenv("JOBTRACKER_MAIL_FOLDER_ALIASES")
    if not raw:
        return dict(DEFAULT_MAIL_FOLDER_ALIASES)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return dict(DEFAULT_MAIL_FOLDER_ALIASES)
    if not isinstance(parsed, dict):
        return dict(DEFAULT_MAIL_FOLDER_ALIASES)
    aliases: dict[str, list[str]] = {}
    for key, value in parsed.items():
        if isinstance(value, list):
            aliases[str(key)] = [str(item) for item in value]
    return aliases or dict(DEFAULT_MAIL_FOLDER_ALIASES)


def _load_own_report_senders() -> frozenset[str]:
    raw = os.getenv("JOBTRACKER_OWN_SENDERS", "")
    if not raw.strip():
        return frozenset()
    return frozenset(item.strip().lower() for item in raw.split(",") if item.strip())


def load_settings() -> Settings:
    load_env_file()
    return Settings(
        db_url=_resolve_db_url(),
        test_db_url=os.getenv("SUPABASE_TEST_DB_URL"),
        supabase_url=os.getenv("SUPABASE_URL"),
        secret_key=os.getenv("SUPABASE_SECRET_KEY"),
        service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        storage_bucket=os.getenv("SUPABASE_STORAGE_BUCKET", "job-artifacts"),
        store_backend=os.getenv("JOBTRACKER_STORE_BACKEND", "sqlite"),
        artifact_backend=os.getenv("JOBTRACKER_ARTIFACT_BACKEND", "local"),
        mail_folder_aliases=_load_mail_folder_aliases(),
        own_report_senders=_load_own_report_senders(),
        s3_artifact_bucket=os.getenv("JOBTRACKER_S3_ARTIFACT_BUCKET"),
        s3_artifact_prefix=os.getenv("JOBTRACKER_S3_ARTIFACT_PREFIX"),
    )


def _load_dotenv_fallback(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
