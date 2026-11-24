from __future__ import annotations

import tempfile
import unittest
import warnings
from pathlib import Path

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

from jobtracker.core.connectors import build_connector
from jobtracker.core.models import ConnectorBuildContext
from jobtracker.mail.generic.maildir import MaildirInbox
from jobtracker.mail.registry import build_alert_parser, build_mail_inbox
from jobtracker.store.generic.memory import MemoryJobStore
from jobtracker.store.generic.sqlite import SqliteJobStore
from jobtracker.store.registry import open_job_store


class ConnectorFactoryTests(unittest.TestCase):
    def test_factory_receives_the_v1_context(self) -> None:
        root = Path("/tmp/project")
        seen: list[ConnectorBuildContext] = []

        def factory(context: ConnectorBuildContext) -> object:
            seen.append(context)
            return object()

        result = build_connector(
            factory,
            ConnectorBuildContext(root=root, slug="example", options={"limit": 2}),
        )

        self.assertIsNotNone(result)
        self.assertEqual(seen[0].root, root)
        self.assertEqual(seen[0].slug, "example")
        self.assertEqual(seen[0].options["limit"], 2)

    def test_zero_argument_classes_are_adapted_with_a_warning(self) -> None:
        class LegacyConnector:
            pass

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            connector = build_connector(
                LegacyConnector,
                ConnectorBuildContext(root=Path("/tmp/project"), slug="legacy", options={}),
            )

        self.assertIsInstance(connector, LegacyConnector)
        self.assertTrue(any(item.category is DeprecationWarning for item in caught))


class StoreFactoryTests(unittest.TestCase):
    def test_sqlite_store_is_root_relative_and_must_be_chosen(self) -> None:
        from jobtracker.db import MissingConfigurationError

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            with self.assertRaises(MissingConfigurationError):
                with open_job_store({}, root=root):
                    pass
            with open_job_store({"backend": "sqlite"}, root=root) as store:
                self.assertIsInstance(store, SqliteJobStore)

            self.assertTrue((root / "outputs/jobsearch.sqlite3").exists())

    def test_memory_store_is_supported(self) -> None:
        with open_job_store({"backend": "memory"}, root=Path("/tmp/project")) as store:
            self.assertIsInstance(store, MemoryJobStore)


class MailFactoryTests(unittest.TestCase):
    def test_rules_parser_is_built_from_config(self) -> None:
        parser = build_alert_parser(
            "example",
            {
                "kind": "rules",
                "senders": ["alerts@provider.example"],
                "subject_patterns": ["new role"],
                "link_patterns": [r"https://jobs\.example/jobs/\d+"],
                "provider_slug": "example",
            },
            root=Path("/tmp/project"),
        )
        message = {
            "from": "alerts@provider.example",
            "subject": "A new role is available",
            "text": "Apply at https://jobs.example/jobs/42",
            "links": ["https://jobs.example/jobs/42"],
        }

        self.assertTrue(parser.matches(message))
        self.assertEqual(parser.parse(message)["links"], ["https://jobs.example/jobs/42"])

    def test_maildir_path_is_resolved_from_root(self) -> None:
        inbox = build_mail_inbox({"kind": "maildir", "path": "private-mail"}, root=Path("/tmp/project"))

        self.assertIsInstance(inbox, MaildirInbox)
        self.assertEqual(inbox.root, Path("/tmp/project/private-mail"))


if __name__ == "__main__":
    unittest.main()
