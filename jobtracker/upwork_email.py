"""Backward-compatible shim for jobtracker.mail.services.upwork."""

from .mail.services.upwork import (
    parse_upwork_alert_payload,
    parse_upwork_source_item,
)

__all__ = ["parse_upwork_alert_payload", "parse_upwork_source_item"]
