"""Extra coverage for notifiers, fetch live path, config, and storage shims."""

from __future__ import annotations

import os
import unittest
from unittest import mock

import httpx
from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

from jobtracker.config import load_settings
from jobtracker.core.models import FetchMetrics
from jobtracker.db import _connect_error_message, _connection_kind, _host_from_db_url
from jobtracker.notify.base import RunReport
from jobtracker.notify.services.slack import SlackNotifier
from jobtracker.notify.services.telegram import TelegramNotifier
from jobtracker.sources.shared.fetch import LiveFetcher
from jobtracker.storage import upload_artifact
from jobtracker.store.artifacts.s3 import S3ArtifactStore


class SlackTelegramNotifierTests(unittest.TestCase):
    def test_slack_health_and_notify(self) -> None:
        empty = SlackNotifier(webhook_url="")
        self.assertTrue(empty.health())
        placeholder = SlackNotifier(webhook_url="{{SLACK_WEBHOOK_URL}}")
        self.assertTrue(placeholder.health())
        notifier = SlackNotifier(webhook_url="https://hooks.slack.example/T")
        self.assertEqual(notifier.health(), [])
        report = RunReport(pipeline="jobboards", run_key="r1", status="ok", summary="done", subject="Hi")
        response = mock.Mock(status_code=200)
        response.raise_for_status = mock.Mock()
        with mock.patch("jobtracker.notify.services.slack.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.post.return_value = response
            result = notifier.notify(report)
        self.assertTrue(result["sent"])
        client.post.assert_called_once()

    def test_telegram_health_and_notify(self) -> None:
        missing = TelegramNotifier(bot_token="", chat_id="")
        self.assertEqual(len(missing.health()), 2)
        placeholder = TelegramNotifier(bot_token="{{TELEGRAM_BOT_TOKEN}}", chat_id="{{TELEGRAM_CHAT_ID}}")
        self.assertEqual(len(placeholder.health()), 2)
        notifier = TelegramNotifier(bot_token="123:abc", chat_id="42")
        self.assertEqual(notifier.health(), [])
        self.assertIn("123:abc", notifier.api_url)
        report = RunReport(pipeline="jobboards", run_key="r1", status="ok", summary="done")
        response = mock.Mock(status_code=200)
        response.raise_for_status = mock.Mock()
        with mock.patch("jobtracker.notify.services.telegram.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.post.return_value = response
            result = notifier.notify(report)
        self.assertTrue(result["sent"])


class LiveFetcherTests(unittest.TestCase):
    def test_get_text_and_json_record_metrics(self) -> None:
        metrics = FetchMetrics()
        fetcher = LiveFetcher(metrics)
        response = mock.Mock()
        response.text = '{"ok": true}'
        response.json.return_value = {"ok": True}
        response.raise_for_status = mock.Mock()
        with mock.patch.object(fetcher._client, "get", return_value=response) as get:
            text = fetcher.get_text("https://example.com/a", "list")
            data = fetcher.get_json("https://example.com/b", "api")
        self.assertEqual(text, '{"ok": true}')
        self.assertEqual(data, {"ok": True})
        self.assertEqual(get.call_count, 2)
        self.assertEqual(metrics.list_request_count, 1)
        self.assertEqual(metrics.api_request_count, 1)
        fetcher.close()

    def test_retries_then_raises(self) -> None:
        metrics = FetchMetrics()
        fetcher = LiveFetcher(metrics, retries=1)
        with mock.patch.object(fetcher._client, "get", side_effect=httpx.TransportError("boom")):
            with self.assertRaises(RuntimeError):
                fetcher.get_text("https://example.com/fail", "list")
        self.assertGreaterEqual(metrics.retry_count, 1)
        fetcher.close()


class ConfigAndDbHelperTests(unittest.TestCase):
    def test_load_settings_defaults_to_local_artifacts(self) -> None:
        with mock.patch("jobtracker.config.load_env_file"):
            with mock.patch.dict(os.environ, {}, clear=True):
                settings = load_settings()

        self.assertEqual(settings.artifact_backend, "local")

    def test_load_settings_reads_env(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "JOBTRACKER_DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/db",
                "SUPABASE_TEST_DB_URL": "postgresql://u:p@127.0.0.1:5432/test",
                "JOBTRACKER_ARTIFACT_BACKEND": "local",
            },
            clear=False,
        ):
            settings = load_settings()
        self.assertIn("127.0.0.1", settings.db_url or "")

    def test_db_url_helpers(self) -> None:
        self.assertEqual(_host_from_db_url("postgresql://u:p@localhost:5432/db"), "localhost")
        self.assertEqual(_connection_kind("postgresql://u:p@db.example:5432/db"), "db.example")
        message = _connect_error_message(
            "JOBTRACKER_DATABASE_URL",
            "postgresql://u:p@127.0.0.1:5432/db",
            Exception("connection refused"),
        )
        self.assertIn("JOBTRACKER_DATABASE_URL", message)


class StorageShimTests(unittest.TestCase):
    def test_storage_reexports_upload_artifact(self) -> None:
        self.assertTrue(callable(upload_artifact))

    def test_s3_module_reexports_store_class(self) -> None:
        self.assertIs(S3ArtifactStore.__name__, "S3ArtifactStore")


if __name__ == "__main__":
    unittest.main()
