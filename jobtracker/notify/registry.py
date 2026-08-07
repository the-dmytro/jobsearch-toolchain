from __future__ import annotations

from typing import Any

from ..core.registry import Registry
from .base import Notifier, RunReport
from .generic.email import EmailNotifier
from .generic.webhook import WebhookNotifier
from .services.slack import SlackNotifier
from .services.telegram import TelegramNotifier

notifier_registry: Registry[Notifier] = Registry("notifier")


def build_notifier(slug: str, config: dict[str, Any]) -> Notifier:
    key = slug.strip().lower()
    if key == "email":
        return EmailNotifier(
            to=str(config.get("to") or ""),
            subject_template=str(config.get("subject_template") or "{subject}"),
            from_address=config.get("from") or config.get("from_address"),
        )
    if key == "webhook":
        return WebhookNotifier(url=str(config.get("url") or ""))
    if key == "slack":
        return SlackNotifier(webhook_url=str(config.get("webhook_url") or config.get("url") or ""))
    if key == "telegram":
        return TelegramNotifier(
            bot_token=str(config.get("bot_token") or ""),
            chat_id=str(config.get("chat_id") or ""),
        )
    return notifier_registry.get(key)


def notify_all(notifiers: list[Notifier], report: RunReport) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for notifier in notifiers:
        results.append({"notifier": notifier.slug, **notifier.notify(report)})
    return results


__all__ = ["Notifier", "RunReport", "notifier_registry", "build_notifier", "notify_all"]
