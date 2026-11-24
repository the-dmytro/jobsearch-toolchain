from __future__ import annotations

import unittest
from importlib.metadata import PackageNotFoundError, distribution, entry_points
from pathlib import Path

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

from jobtracker.core.connectors import build_connector
from jobtracker.core.models import ConnectorBuildContext
from jobtracker.mail.base import OutgoingMessage
from jobtracker.notify.base import RunReport

try:
    distribution("jobtracker-fixture-connectors")
except PackageNotFoundError:
    PLUGIN_INSTALLED = False
else:
    PLUGIN_INSTALLED = True


def _fixture(group: str):
    matches = [entry for entry in entry_points(group=group) if entry.name.startswith("fixture-")]
    if len(matches) != 1:
        raise AssertionError(f"expected one fixture in {group}, found {len(matches)}")
    entry = matches[0]
    context = ConnectorBuildContext(root=Path.cwd(), slug=entry.name, options={"fixture": True})
    return build_connector(entry.load(), context)


@unittest.skipUnless(PLUGIN_INSTALLED, "install examples/plugins/fixture-connectors")
class FixturePluginContractTests(unittest.TestCase):
    def test_source_factory_contract(self) -> None:
        source = _fixture("jobtracker.sources")

        self.assertEqual(source.slug, "fixture-source")
        self.assertTrue(callable(source.discover))
        self.assertTrue(callable(source.health))

    def test_parser_factory_contract(self) -> None:
        parser = _fixture("jobtracker.mail.parsers")
        message = {"subject": "Fixture alert", "links": ["https://jobs.example.invalid/1"]}

        self.assertTrue(parser.matches(message))
        self.assertEqual(parser.parse(message)["provider_slug"], "fixture")

    def test_inbox_factory_contract(self) -> None:
        inbox = _fixture("jobtracker.mail.inboxes")

        self.assertEqual(inbox.resolve_folder("fixture"), "fixture")
        self.assertEqual(len(inbox.fetch_messages("fixture")), 1)

    def test_sender_factory_contract(self) -> None:
        sender = _fixture("jobtracker.mail.senders")
        receipt = sender.send(
            OutgoingMessage(
                sender="reports@example.com",
                recipient="person@example.com",
                subject="Fixture report",
                body="Fictitious body",
            )
        )

        self.assertTrue(receipt.sent)

    def test_store_factory_contract(self) -> None:
        store = _fixture("jobtracker.stores")

        for operation in ("upsert_run_payload", "check_duplicates", "export_application_summary"):
            self.assertTrue(callable(getattr(store, operation)))

    def test_notifier_factory_contract(self) -> None:
        notifier = _fixture("jobtracker.notifiers")
        report = RunReport(
            pipeline="fixture",
            run_key="fixture-1",
            status="completed",
            summary="Fixture completed",
            subject="Fixture report",
            body="Fictitious body",
        )

        self.assertEqual(notifier.health(), [])
        self.assertTrue(notifier.notify(report)["sent"])


if __name__ == "__main__":
    unittest.main()
