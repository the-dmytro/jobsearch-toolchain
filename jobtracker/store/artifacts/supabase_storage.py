from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ...config import load_settings
from ..base import ArtifactRef, ArtifactStore
from .local import file_sha256


class SupabaseArtifactStore:
    def upload(self, path: str | Path, storage_path: str | None = None) -> ArtifactRef:
        local_path = Path(path)
        settings = load_settings()
        destination = storage_path or local_path.name
        metadata: dict[str, Any] = {
            "local_path": str(local_path),
            "sha256": file_sha256(local_path),
            "size_bytes": local_path.stat().st_size,
            "storage_bucket": settings.storage_bucket,
            "storage_path": destination,
            "backend": "supabase",
        }

        api_key = settings.secret_key or settings.service_role_key
        if not settings.supabase_url or not api_key:
            return ArtifactRef(
                local_path=str(local_path),
                storage_bucket=settings.storage_bucket,
                storage_path=destination,
                sha256=metadata["sha256"],
                size_bytes=metadata["size_bytes"],
                uploaded=False,
                upload_warning="SUPABASE_URL and SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY are required for Storage upload.",
                metadata=metadata,
            )

        try:
            from supabase import create_client
        except ImportError as exc:
            raise RuntimeError(
                "supabase is required for Storage upload. Install dependencies with `python3 -m pip install -r requirements.txt`."
            ) from exc

        client = create_client(settings.supabase_url, api_key)
        content = local_path.read_bytes()
        try:
            client.storage.from_(settings.storage_bucket).upload(destination, content, {"upsert": "true"})
        except Exception:
            client.storage.from_(settings.storage_bucket).update(destination, content)
        return ArtifactRef(
            local_path=str(local_path),
            storage_bucket=settings.storage_bucket,
            storage_path=destination,
            sha256=metadata["sha256"],
            size_bytes=metadata["size_bytes"],
            uploaded=True,
            metadata=metadata,
        )


def upload_artifact(path: str | Path, storage_path: str | None = None) -> dict[str, Any]:
    return SupabaseArtifactStore().upload(path, storage_path=storage_path).as_dict()
