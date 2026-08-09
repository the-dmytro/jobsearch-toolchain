from __future__ import annotations

import unittest
from importlib.metadata import EntryPoint
from unittest.mock import MagicMock, patch

from jobtracker.core import Registry, UnknownConnectorError


class _BuiltinConnector:
    slug = "builtin"


class _PluginConnector:
    slug = "plugin"


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry: Registry[_BuiltinConnector] = Registry("source")

    def test_register_and_get(self) -> None:
        connector = _BuiltinConnector()
        self.registry.register(connector)

        resolved = self.registry.get("builtin")

        self.assertIs(resolved, connector)
        self.assertEqual(self.registry.all(), {"builtin": connector})

    def test_register_with_explicit_slug_decorator(self) -> None:
        @self.registry.register("custom")
        class CustomConnector:
            pass

        self.assertIs(self.registry.get("custom"), CustomConnector)

    def test_unknown_slug_lists_available_connectors(self) -> None:
        self.registry.register(_BuiltinConnector())

        with self.assertRaises(UnknownConnectorError) as ctx:
            self.registry.get("missing")

        self.assertIn("missing", str(ctx.exception))
        self.assertIn("builtin", str(ctx.exception))

    @patch("jobtracker.core.registry._iter_entry_points")
    def test_load_entry_points_uses_mock_loader(self, iter_entry_points: MagicMock) -> None:
        plugin = _PluginConnector()
        entry_point = MagicMock(spec=EntryPoint)
        entry_point.name = "plugin"
        entry_point.group = "jobtracker.sources"
        entry_point.load.return_value = plugin
        iter_entry_points.return_value = [entry_point]

        self.registry.load_entry_points("jobtracker.sources")

        self.assertIs(self.registry.get("plugin"), plugin)

    @patch("jobtracker.core.registry._iter_entry_points")
    def test_in_tree_registration_takes_precedence_over_entry_points(
        self, iter_entry_points: MagicMock
    ) -> None:
        builtin = _BuiltinConnector()
        self.registry.register(builtin)

        entry_point = MagicMock(spec=EntryPoint)
        entry_point.name = "builtin"
        entry_point.group = "jobtracker.sources"
        replacement = _PluginConnector()
        iter_entry_points.return_value = [entry_point]

        with patch.object(entry_point, "load", return_value=replacement):
            self.registry.load_entry_points("jobtracker.sources")

        self.assertIs(self.registry.get("builtin"), builtin)


if __name__ == "__main__":
    unittest.main()
