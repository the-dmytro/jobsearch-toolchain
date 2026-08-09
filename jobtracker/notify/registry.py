from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..core.connectors import ConnectorSpec
from ..core.models import ConnectorBuildContext
from ..core.registry import Registry
from .base import Notifier, RunReport
from .generic.email import EmailNotifier
from .generic.webhook import WebhookNotifier
from .services.slack import SlackNotifier
from .services.telegram import TelegramNotifier

notifier_registry: Registry[Any] = Registry("notifier")


def _load_notifier_entry_point(entry_point: Any) -> ConnectorSpec:
    return ConnectorSpec(slug=entry_point.name, loaded=entry_point.load())


def _register_builtin_notifiers() -> None:
    notifier_registry.register(EmailNotifier(to=""))
    notifier_registry.register(WebhookNotifier(url=""))
    notifier_registry.register(SlackNotifier(webhook_url=""))
    notifier_registry.register(TelegramNotifier(bot_token="", chat_id=""))


_register_builtin_notifiers()
notifier_registry.load_entry_points("jobtracker.notifiers", entry_point_loader=_load_notifier_entry_point)


def _option(config: dict[str, Any], name: str, *aliases: str) -> str:
    for key in (name, *aliases):
        value = str(config.get(key) or "").strip()
        if value:
            return value
    for key in (name, *aliases):
        env_name = str(config.get(f"{key}_env") or "").strip()
        if env_name:
            return str(os.getenv(env_name) or "").strip()
    return ""


def build_notifier(slug: str, config: dict[str, Any], *, root: Path | None = None) -> Notifier:
    key = slug.strip().lower()
    if key == "email":
        return EmailNotifier(
            to=_option(config, "to"),
            subject_template=str(config.get("subject_template") or "{subject}"),
            from_address=_option(config, "from", "from_address") or None,
        )
    if key == "webhook":
        return WebhookNotifier(url=_option(config, "url"))
    if key == "slack":
        return SlackNotifier(webhook_url=_option(config, "webhook_url", "url"))
    if key == "telegram":
        return TelegramNotifier(
            bot_token=_option(config, "bot_token"),
            chat_id=_option(config, "chat_id"),
        )
    item = notifier_registry.get(key)
    if isinstance(item, ConnectorSpec):
        return item.build(ConnectorBuildContext(root or Path.cwd(), key, dict(config)))
    return item


def notify_all(notifiers: list[Notifier], report: RunReport) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for notifier in notifiers:
        results.append({"notifier": notifier.slug, **notifier.notify(report)})
    return results


__all__ = ["Notifier", "RunReport", "notifier_registry", "build_notifier", "notify_all"]
