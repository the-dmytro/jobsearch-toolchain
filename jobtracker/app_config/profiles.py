from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from .schema import ConfigValidationError, validate_profile_config


@dataclass(frozen=True)
class JobboardProfile:
    slug: str
    name: str
    output_slug: str
    targets_path: Path
    report_path_template: str
    email_body_template: str
    email_subject_prefix: str
    profile_files: tuple[str, ...]
    evaluation_notes: tuple[str, ...]
    email_to: str | None = None

    @classmethod
    def from_validated(cls, data: dict[str, str | tuple[str, ...] | None]) -> "JobboardProfile":
        return cls(
            slug=str(data["slug"]),
            name=str(data["name"]),
            output_slug=str(data["output_slug"]),
            targets_path=Path(str(data["targets_path"])),
            report_path_template=str(data["report_path_template"]),
            email_body_template=str(data["email_body_template"]),
            email_subject_prefix=str(data["email_subject_prefix"]),
            profile_files=tuple(str(item) for item in (data.get("profile_files") or ())),
            evaluation_notes=tuple(str(item) for item in (data.get("evaluation_notes") or ())),
            email_to=data.get("email_to") if data.get("email_to") else None,
        )


def _profile_path(profile_dir: Path, slug: str) -> Path:
    return profile_dir / f"{slug}.toml"


def _resolve_targets_path(targets_path: Path, *, root: Path | None = None) -> Path:
    if targets_path.exists():
        return targets_path
    if root and not targets_path.is_absolute():
        rooted = root / targets_path
        if rooted.exists():
            return rooted
    legacy = Path("jobtracker") / targets_path.name
    if legacy.exists():
        return legacy
    return targets_path


def load_profile(slug: str, profile_dir: str | Path = "profile") -> JobboardProfile:
    directory = Path(profile_dir)
    path = _profile_path(directory, slug)
    if not path.exists():
        raise ConfigValidationError(f"Profile not found: {path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    validated = validate_profile_config(data, source_path=path)
    targets_path = _resolve_targets_path(Path(str(validated["targets_path"])), root=directory.parent)
    validated["targets_path"] = str(targets_path)
    return JobboardProfile.from_validated(validated)


def load_profiles(profile_dir: str | Path = "profile") -> dict[str, JobboardProfile]:
    directory = Path(profile_dir)
    if not directory.exists():
        return {}
    profiles: dict[str, JobboardProfile] = {}
    for path in sorted(directory.glob("*.toml")):
        if path.name.endswith(".example.toml"):
            continue
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        validated = validate_profile_config(data, source_path=path)
        profile = JobboardProfile.from_validated(validated)
        profiles[profile.slug] = profile
    return profiles
