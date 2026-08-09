from __future__ import annotations

import inspect
import warnings
from dataclasses import dataclass
from typing import Any

from .models import ConnectorBuildContext


@dataclass(frozen=True)
class ConnectorSpec:
    slug: str
    loaded: Any

    def build(self, context: ConnectorBuildContext) -> Any:
        return build_connector(self.loaded, context)


def build_connector(loaded: Any, context: ConnectorBuildContext) -> Any:
    """Build a v1 connector and temporarily adapt legacy plugin objects."""
    if inspect.isfunction(loaded) or inspect.ismethod(loaded) or inspect.isclass(loaded):
        try:
            inspect.signature(loaded).bind(context)
        except TypeError:
            warnings.warn(
                f"Connector {context.slug!r} uses the deprecated zero-argument plugin form",
                DeprecationWarning,
                stacklevel=2,
            )
            return loaded()
        return loaded(context)
    warnings.warn(
        f"Connector {context.slug!r} uses the deprecated pre-built instance form",
        DeprecationWarning,
        stacklevel=2,
    )
    return loaded
