from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from .schema import ConfigValidationError, validate_jobsearch_config

DEFAULT_CONFIG_PATH = Path("config/jobsearch.toml")
EXAMPLE_CONFIG_PATH = Path("config/jobsearch.example.toml")
LOCAL_CONFIG_SUFFIX = ".local.toml"
ENVIRONMENT_ENV = "JOBTRACKER_ENVIRONMENT"
ENVIRONMENTS_DIR = "environments"


@dataclass(frozen=True)
class AppConfig:
    root: Path
    schema_version: int
    paths: dict[str, str]
    store: dict[str, Any]
    source_configs: dict[str, dict[str, Any]]
    mail: dict[str, Any]
    pipelines: dict[str, dict[str, Any]]
    notify: dict[str, dict[str, Any]]
    sources: list[Path]
    environment: str | None = None

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.root / path

    @property
    def config_dir(self) -> Path:
        return self.resolve_path(self.paths["config_dir"])

    @property
    def profile_dir(self) -> Path:
        return self.resolve_path(self.paths["profile_dir"])

    @property
    def output_dir(self) -> Path:
        return self.resolve_path(self.paths["output_dir"])

    @property
    def payload_dir(self) -> Path:
        return self.resolve_path(self.paths["payload_dir"])

    @property
    def store_path(self) -> Path:
        return self.resolve_path(self.store["sqlite_path"])

    @property
    def artifact_dir(self) -> Path:
        return self.resolve_path(self.store["artifact_local_path"])


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def load_app_config(
    config_path: str | Path | None = None,
    *,
    root: str | Path | None = None,
) -> AppConfig:
    project_root = Path(root or Path.cwd())
    if not project_root.is_absolute():
        project_root = Path.cwd() / project_root
    primary = Path(config_path) if config_path else project_root / DEFAULT_CONFIG_PATH
    if not primary.is_absolute():
        primary = project_root / primary
    if not primary.exists():
        raise ConfigValidationError(f"Config file not found: {primary}")

    merged = _load_toml(primary)
    environment, environment_path = _selected_environment(primary.parent)
    if environment_path is not None:
        merged = _deep_merge(merged, _load_toml(environment_path))
    local_path = primary.with_name(primary.stem + LOCAL_CONFIG_SUFFIX)
    local = _load_toml(local_path)
    blocked = sorted(set((local.get("store") or {})) & {"backend", "connector", "hosting"})
    if blocked:
        raise ConfigValidationError(
            f"{local_path.name} must not set store.{', store.'.join(blocked)}: the database choice belongs in "
            "config/jobsearch.toml and config/environments/<name>.toml."
        )
    merged = _deep_merge(merged, local)
    if "schema_version" not in merged:
        warnings.warn(
            "Config without schema_version is deprecated; add schema_version = 1 before v0.3",
            DeprecationWarning,
            stacklevel=2,
        )
    validated = validate_jobsearch_config(merged)
    _require_connector(validated["store"], primary.parent, environment)
    if environment:
        validated["store"]["environment"] = environment
    sources = [primary]
    if environment_path is not None:
        sources.append(environment_path)
    if local_path.exists():
        sources.append(local_path)
    return AppConfig(
        root=project_root,
        schema_version=validated["schema_version"],
        paths=validated["paths"],
        store=validated["store"],
        source_configs=validated["sources"],
        mail=validated["mail"],
        pipelines=validated["pipelines"],
        notify=validated["notify"],
        sources=sources,
        environment=environment,
    )


def environment_files(config_dir: Path) -> list[str]:
    directory = config_dir / ENVIRONMENTS_DIR
    return sorted(path.stem for path in directory.glob("*.toml")) if directory.is_dir() else []


def _selected_environment(config_dir: Path) -> tuple[str | None, Path | None]:
    """The environment named by JOBTRACKER_ENVIRONMENT; never guessed."""
    from ..config import load_env_file

    load_env_file()
    name = (os.getenv(ENVIRONMENT_ENV) or "").strip()
    if not name:
        return None, None
    if not name.replace("-", "").replace("_", "").isalnum():
        raise ConfigValidationError(f"{ENVIRONMENT_ENV} must be a simple name, got {name!r}")
    path = config_dir / ENVIRONMENTS_DIR / f"{name}.toml"
    if not path.exists():
        available = ", ".join(environment_files(config_dir)) or "(none)"
        raise ConfigValidationError(
            f"{ENVIRONMENT_ENV}={name!r} but {path} does not exist. Available environments: {available}"
        )
    return name, path


def _require_connector(store: dict[str, Any], config_dir: Path, environment: str | None) -> None:
    if store.get("backend") != "postgres" or store.get("connector"):
        return
    available = ", ".join(environment_files(config_dir)) or "(none)"
    where = (
        f"config/environments/{environment}.toml"
        if environment
        else (
            f"config/environments/<name>.toml and select it with {ENVIRONMENT_ENV} (available: {available})"
        )
    )
    raise ConfigValidationError(
        f"store.connector is required for the PostgreSQL store; set it in {where}. "
        "Run `jobtracker probe-environment` to see which connectors this environment can use."
    )
