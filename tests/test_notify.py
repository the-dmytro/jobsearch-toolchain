from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from jobtracker.notify.base import RunReport
from jobtracker.notify.generic.email import EmailNotifier
from jobtracker.notify.generic.webhook import WebhookNotifier
from jobtracker.notify.registry import build_notifier, notify_all
from jobtracker.notify.services.slack import SlackNotifier
from jobtracker.notify.services.telegram import TelegramNotifier


class NotifyTests(unittest.TestCase):
    def test_build_notifier_email(self) -> None:
        notifier = build_notifier("email", {"to": "ops@example.com"})
        self.assertIsInstance(notifier, EmailNotifier)
        self.assertEqual(notifier.to, "ops@example.com")

    def test_build_notifier_webhook(self) -> None:
        notifier = build_notifier("webhook", {"url": "https://example.com/hook"})
        self.assertIsInstance(notifier, WebhookNotifier)

    def test_build_notifier_slack_and_telegram(self) -> None:
        slack = build_notifier("slack", {"webhook_url": "https://hooks.slack.com/services/test"})
        telegram = build_notifier("telegram", {"bot_token": "token", "chat_id": "123"})
        self.assertIsInstance(slack, SlackNotifier)
        self.assertIsInstance(telegram, TelegramNotifier)

    def test_webhook_health_flags_placeholder_url(self) -> None:
        notifier = WebhookNotifier(url="{{WEBHOOK_URL}}")
        issues = notifier.health()
        self.assertTrue(issues)

    @patch("jobtracker.notify.generic.webhook.httpx.Client")
    def test_notify_all_posts_webhook_payload(self, client_cls: MagicMock) -> None:
        response = MagicMock()
        response.status_code = 200
        client = MagicMock()
        client.__enter__.return_value = client
        client.post.return_value = response
        client_cls.return_value = client

        report = RunReport(
            pipeline="jobboards",
            run_key="ua-jobboards-2026-04-29",
            status="completed",
            summary="Prepared 3 opportunities",
        )
        results = notify_all([WebhookNotifier(url="https://example.com/hook")], report)
        self.assertEqual(results[0]["status_code"], 200)
        client.post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
