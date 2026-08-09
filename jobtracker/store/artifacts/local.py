from __future__ import annotations

import hashlib
from pathlib import Path

from ...config import load_settings
from ..base import ArtifactRef, ArtifactStore


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LocalArtifactStore:
    def upload(self, path: str | Path, storage_path: str | None = None) -> ArtifactRef:
        local_path = Path(path)
        destination = storage_path or local_path.name
        return ArtifactRef(
            local_path=str(local_path),
            storage_path=destination,
            sha256=file_sha256(local_path),
            size_bytes=local_path.stat().st_size,
            uploaded=False,
            metadata={"backend": "local"},
        )


class S3ArtifactStore:
    def __init__(self, bucket: str | None = None, prefix: str = "") -> None:
        settings = load_settings()
        self.bucket = bucket or settings.s3_artifact_bucket
        self.prefix = prefix or settings.s3_artifact_prefix or ""
        if not self.bucket:
            raise RuntimeError("S3 artifact bucket is required for S3ArtifactStore.")

    def upload(self, path: str | Path, storage_path: str | None = None) -> ArtifactRef:
        local_path = Path(path)
        destination = storage_path or local_path.name
        if self.prefix:
            destination = f"{self.prefix.rstrip('/')}/{destination}"
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3 artifact upload.") from exc
        client = boto3.client("s3")
        content = local_path.read_bytes()
        client.put_object(Bucket=self.bucket, Key=destination, Body=content)
        return ArtifactRef(
            local_path=str(local_path),
            storage_bucket=self.bucket,
            storage_path=destination,
            sha256=file_sha256(local_path),
            size_bytes=local_path.stat().st_size,
            uploaded=True,
            metadata={"backend": "s3"},
        )


def artifact_store_factory(backend: str | None = None) -> ArtifactStore:
    settings = load_settings()
    resolved = backend or settings.artifact_backend
    if resolved == "local":
        return LocalArtifactStore()
    if resolved == "s3":
        return S3ArtifactStore()
    if resolved == "supabase":
        from .supabase_storage import SupabaseArtifactStore

        return SupabaseArtifactStore()
    raise ValueError(f"Unsupported artifact backend: {resolved}")
