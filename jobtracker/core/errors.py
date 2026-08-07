from __future__ import annotations

from jobtracker.db import MissingConfigurationError


class UnknownConnectorError(LookupError):
    pass


class ConnectorHealthError(RuntimeError):
    pass


__all__ = [
    "ConnectorHealthError",
    "MissingConfigurationError",
    "UnknownConnectorError",
]
