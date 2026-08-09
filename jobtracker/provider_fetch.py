"""Compatibility shim — re-exports from sources.registry and core.models."""

from __future__ import annotations

from jobtracker.core.models import Candidate, CollectionResult, ExistingRef, FetchMetrics
from jobtracker.sources.registry import benchmark_providers, collect_provider_run
from jobtracker.sources.shared.fetch import (
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    FIXTURE_ROOT,
    USER_AGENT,
    FixtureFetcher,
    LiveFetcher,
)
from jobtracker.sources.shared.infer import _matches_lane
from jobtracker.sources.shared.payload import DEFAULT_OUTPUT_DIR

__all__ = [
    "Candidate",
    "CollectionResult",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_RETRIES",
    "DEFAULT_TIMEOUT_SECONDS",
    "ExistingRef",
    "FetchMetrics",
    "FIXTURE_ROOT",
    "FixtureFetcher",
    "LiveFetcher",
    "USER_AGENT",
    "_matches_lane",
    "benchmark_providers",
    "collect_provider_run",
]
