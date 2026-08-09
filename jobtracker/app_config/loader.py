from __future__ import annotations

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
    local_path = primary.with_name(primary.stem + LOCAL_CONFIG_SUFFIX)
    merged = _deep_merge(merged, _load_toml(local_path))
    if "schema_version" not in merged:
        warnings.warn(
            "Config without schema_version is deprecated; add schema_version = 1 before v0.3",
            DeprecationWarning,
            stacklevel=2,
        )
    validated = validate_jobsearch_config(merged)
    sources = [primary]
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
    )
