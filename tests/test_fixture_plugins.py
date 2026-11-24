from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from jobtracker.core.models import CollectionContext, ConnectorBuildContext, FetchMetrics
from jobtracker.mail.base import OutgoingMessage
from jobtracker.notify.base import RunReport

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "examples/plugins/fixture-connectors"
SPEC = importlib.util.spec_from_file_location(
    "jobtracker_fixture_connectors",
    PLUGIN_ROOT / "jobtracker_fixture_connectors/__init__.py",
)
assert SPEC and SPEC.loader
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


class FixturePluginTests(unittest.TestCase):
    def context(self, slug: str) -> ConnectorBuildContext:
        return ConnectorBuildContext(ROOT, slug, {})

    def test_package_declares_every_v1_entry_point_group(self) -> None:
        data = tomllib.loads((PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        groups = data["project"]["entry-points"]

        self.assertEqual(
            set(groups),
            {
                "jobtracker.sources",
                "jobtracker.mail.parsers",
                "jobtracker.mail.inboxes",
                "jobtracker.mail.senders",
                "jobtracker.stores",
                "jobtracker.notifiers",
            },
        )

    def test_source_parser_inbox_sender_and_notifier_contracts(self) -> None:
        source = fixture.build_source(self.context("fixture-source"))
        metrics = FetchMetrics()
        candidates, status, blockers = source.discover(
            CollectionContext(metrics=metrics, provider_slug="fixture_source")
        )
        self.assertEqual((status, blockers, len(candidates)), ("completed", [], 1))

        parser = fixture.build_parser(self.context("fixture-parser"))
        self.assertIsNotNone(parser.parse({"subject": "Fixture alert", "links": []}))

        inbox = fixture.build_inbox(self.context("fixture-inbox"))
        self.assertEqual(inbox.list_folders(), ["fixture"])

        sender = fixture.build_sender(self.context("fixture-sender"))
        receipt = sender.send(OutgoingMessage("from@example.com", "to@example.com", "Fixture", "Body"))
        self.assertTrue(receipt.sent)

        notifier = fixture.build_notifier(self.context("fixture-notifier"))
        report = RunReport("demo", "fixture-run", "completed", "done", "Fixture", "Body")
        self.assertTrue(notifier.notify(report)["sent"])
        self.assertEqual(notifier.health(), [])

    def test_store_contract_round_trip(self) -> None:
        store = fixture.build_store(self.context("fixture-store"))
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = Path(temp_dir) / "payload.json"
            payload.write_text(
                '{"run":{"run_key":"fixture-run","status":"completed"},"source_items":[],"opportunities":[]}',
                encoding="utf-8",
            )
            result = store.upsert_run_payload("fixture", str(payload))

        self.assertEqual(result.run_key, "fixture-run")
        self.assertEqual(store.check_duplicates("fixture", None, None), [])
        self.assertIn("application", store.export_application_summary("fixture-app").lower())


if __name__ == "__main__":
    unittest.main()
