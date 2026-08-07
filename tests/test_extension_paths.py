"""Tests for the three documented connector extension paths.

1. config-only — a generic base (here ``JsonLdSource``) given a slug and options
2. in-tree — a class put into ``source_registry`` by ``@register_source``
3. plugin — a ``jobtracker.sources`` entry point loaded into a ``Registry``

The entry-point path is exercised against throwaway ``Registry`` instances so
the global registries are never mutated.
"""

from __future__ import annotations

import json
import unittest
from typing import Any
from unittest import mock

from jobtracker.core import registry as core_registry
from jobtracker.core.errors import UnknownConnectorError
from jobtracker.core.models import Candidate, CollectionContext, FetchMetrics
from jobtracker.core.registry import Registry
from jobtracker.notify.registry import notifier_registry
from jobtracker.sources import registry as sources_registry
from jobtracker.sources.generic.jsonld import JsonLdSource
from jobtracker.sources.shared.fetch import FIXTURE_ROOT

JSON_LD_HTML = """
<!doctype html>
<html><head>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "identifier": "acme-ios-101",
    "title": "Senior iOS Engineer",
    "url": "https://careers.acme.example/jobs/acme-ios-101",
    "datePosted": "2026-04-20T09:00:00+00:00",
    "employmentType": "Full-time",
    "jobLocationType": "TELECOMMUTE",
    "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
    "description": "<p>Own the SwiftUI checkout flow.</p>"
  }
  </script>
</head><body></body></html>
"""

ROLE_LANE = {"name": "iOS/macOS", "include_terms": ["ios", "swiftui"], "exclude_terms": ["android"]}


class FakeFetcher:
    """Serves a single canned response for any URL."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[tuple[str, str]] = []
        self.closed = False

    def get_text(self, url: str, kind: str) -> str:
        self.requests.append((url, kind))
        return self.text

    def get_json(self, url: str, kind: str) -> Any:
        return json.loads(self.get_text(url, kind))

    def close(self) -> None:
        self.closed = True


class ConfigOnlyConnectorTests(unittest.TestCase):
    """A `[sources.acme] kind = "jsonld"` connector needs no Python at all."""

    def build_context(self, fetcher: FakeFetcher, options: dict[str, Any]) -> CollectionContext:
        return CollectionContext(
            conn=None,
            fetcher=fetcher,
            targets={"role_lane": ROLE_LANE},
            metrics=FetchMetrics(),
            provider_slug="acme",
            options=options,
        )

    def test_a_slugged_jsonld_source_discovers_candidates(self) -> None:
        source = JsonLdSource()
        source.slug = "acme"
        fetcher = FakeFetcher(JSON_LD_HTML)
        ctx = self.build_context(fetcher, {"listing_url": "https://careers.acme.example/jobs"})

        candidates, status, blockers = source.discover(ctx)

        self.assertEqual(status, "completed")
        self.assertEqual(blockers, [])
        self.assertEqual(len(candidates), 1)
        self.assertIsInstance(candidates[0], Candidate)
        self.assertEqual(candidates[0].external_id, "acme-ios-101")
        self.assertEqual(candidates[0].company, "Acme Corp")
        self.assertEqual(candidates[0].metadata["provider"], "acme")
        self.assertEqual(fetcher.requests, [("https://careers.acme.example/jobs", "list")])

    def test_the_slug_only_relabels_the_instance(self) -> None:
        source = JsonLdSource()
        source.slug = "acme"

        self.assertEqual(source.slug, "acme")
        self.assertEqual(JsonLdSource.slug, "jsonld")
        self.assertEqual(JsonLdSource().slug, "jsonld")

    def test_the_generic_base_satisfies_the_job_source_protocol(self) -> None:
        source = JsonLdSource()
        ctx = self.build_context(FakeFetcher(JSON_LD_HTML), {})

        self.assertTrue(hasattr(source, "slug"))
        self.assertEqual(source.health(ctx), [])
        self.assertEqual(len(source.discover(ctx)), 3)


class InTreeRegistrationTests(unittest.TestCase):
    """`@register_source` puts a class into the module-level source registry."""

    def test_the_builtin_service_connectors_are_registered_by_slug(self) -> None:
        registered = sources_registry.source_registry.all()

        self.assertLessEqual({"ashby", "lever", "greenhouse"}, set(registered))
        self.assertEqual(registered["ashby"].slug, "ashby")

    def test_register_source_returns_the_class_and_stores_an_instance(self) -> None:
        registered = sources_registry.source_registry

        def _cleanup() -> None:
            registered.all().pop("acme_in_tree", None)
            registered._items.pop("acme_in_tree", None)

        self.addCleanup(_cleanup)

        @sources_registry.register_source
        class AcmeInTreeSource:
            slug = "acme_in_tree"

        self.assertIs(AcmeInTreeSource.slug, "acme_in_tree")
        self.assertIsInstance(registered.get("acme_in_tree"), AcmeInTreeSource)

    def test_collect_provider_run_rejects_unregistered_slugs(self) -> None:
        with self.assertRaises(UnknownConnectorError) as caught:
            sources_registry.collect_provider_run("telepathy", dry_run=True, fixture_dir=FIXTURE_ROOT)

        self.assertIn("telepathy", str(caught.exception))

    def test_resolve_source_builds_generic_from_kind(self) -> None:
        source = sources_registry.resolve_source("acme", source_config={"kind": "jsonld"})
        self.assertEqual(source.slug, "acme")
        self.assertIsInstance(source, JsonLdSource)

    def test_build_generic_source_accepts_json_api_alias(self) -> None:
        source = sources_registry.build_generic_source("json-api", "boards")
        self.assertEqual(source.slug, "boards")

    def test_load_source_entry_point_instantiates_classes(self) -> None:
        entry = FakeEntryPoint("plugin_board", PluginSource)
        loaded = sources_registry._load_source_entry_point(entry)
        self.assertIsInstance(loaded, PluginSource)
        self.assertEqual(loaded.slug, "plugin_board")


class RegistryTests(unittest.TestCase):
    """In-tree registration behaviour, exercised on isolated registries."""

    def test_register_accepts_a_bare_class_and_an_explicit_slug(self) -> None:
        registry: Registry[Any] = Registry("source")

        class AcmeSource:
            slug = "acme"

        instance = AcmeSource()
        registry.register(instance)
        registry.register("alias")(instance)

        self.assertIs(registry.get("acme"), instance)
        self.assertIs(registry.get("alias"), instance)
        self.assertEqual(set(registry.all()), {"acme", "alias"})

    def test_lookups_are_case_and_whitespace_insensitive(self) -> None:
        registry: Registry[Any] = Registry("source")

        class AcmeSource:
            slug = "acme"

        registry.register(AcmeSource())

        self.assertIsNotNone(registry.get("  ACME "))

    def test_unknown_slugs_list_what_is_available(self) -> None:
        registry: Registry[Any] = Registry("source")

        class AcmeSource:
            slug = "acme"

        registry.register(AcmeSource())

        with self.assertRaises(UnknownConnectorError) as caught:
            registry.get("nope")

        self.assertIn("Unknown source 'nope'", str(caught.exception))
        self.assertIn("Available: acme", str(caught.exception))

    def test_items_without_a_slug_are_rejected(self) -> None:
        registry: Registry[Any] = Registry("source")

        with self.assertRaises(ValueError):
            registry.register(object())

    def test_all_returns_a_copy(self) -> None:
        registry: Registry[Any] = Registry("source")

        class AcmeSource:
            slug = "acme"

        registry.register(AcmeSource())
        snapshot = registry.all()
        snapshot.clear()

        self.assertEqual(set(registry.all()), {"acme"})

    def test_the_notifier_registry_is_a_registry(self) -> None:
        self.assertIsInstance(notifier_registry, Registry)


class FakeEntryPoint:
    def __init__(self, name: str, value: Any) -> None:
        self.name = name
        self.group = "jobtracker.sources"
        self._value = value
        self.load_count = 0

    def load(self) -> Any:
        self.load_count += 1
        return self._value


class PluginSource:
    slug = "plugin_board"

    def health(self, ctx: CollectionContext) -> list[str]:
        return []

    def discover(self, ctx: CollectionContext) -> tuple[list[Candidate], str, list[str]]:
        return [], "completed", []


def instantiating_loader(entry_point: Any) -> Any:
    """The loader a host would pass to turn plugin classes into instances."""

    loaded = entry_point.load()
    return loaded() if isinstance(loaded, type) else loaded


class EntryPointPluginTests(unittest.TestCase):
    """Third-party packages register connectors through entry points."""

    def load_into(self, registry: Registry[Any], entry_points: list[FakeEntryPoint], **kwargs) -> None:
        with mock.patch.object(core_registry, "_iter_entry_points", return_value=entry_points):
            registry.load_entry_points("jobtracker.sources", **kwargs)

    def test_the_default_loader_stores_the_entry_point_value_verbatim(self) -> None:
        registry: Registry[Any] = Registry("source")
        entry_point = FakeEntryPoint("plugin_board", PluginSource)

        self.load_into(registry, [entry_point])

        self.assertEqual(set(registry.all()), {"plugin_board"})
        self.assertEqual(entry_point.load_count, 1)
        self.assertIs(registry.get("plugin_board"), PluginSource)

    def test_a_custom_loader_can_instantiate_the_plugin_class(self) -> None:
        registry: Registry[Any] = Registry("source")

        self.load_into(registry, [FakeEntryPoint("plugin_board", PluginSource)], entry_point_loader=instantiating_loader)

        loaded = registry.get("plugin_board")
        self.assertIsInstance(loaded, PluginSource)
        self.assertEqual(loaded.slug, "plugin_board")

    def test_the_entry_point_name_keys_the_registry_not_the_class_slug(self) -> None:
        registry: Registry[Any] = Registry("source")

        self.load_into(registry, [FakeEntryPoint("Community_Board", PluginSource)])

        self.assertEqual(set(registry.all()), {"community_board"})
        with self.assertRaises(UnknownConnectorError):
            registry.get("plugin_board")

    def test_already_registered_slugs_are_not_overwritten_by_plugins(self) -> None:
        registry: Registry[Any] = Registry("source")
        builtin = PluginSource()
        registry.register(builtin)
        entry_point = FakeEntryPoint("plugin_board", PluginSource)

        self.load_into(registry, [entry_point])

        self.assertIs(registry.get("plugin_board"), builtin)
        self.assertEqual(entry_point.load_count, 0)

    def test_loading_an_empty_group_is_a_no_op(self) -> None:
        registry: Registry[Any] = Registry("source")

        self.load_into(registry, [])

        self.assertEqual(registry.all(), {})

    def test_the_real_entry_point_iterator_returns_an_iterable(self) -> None:
        self.assertIsNotNone(list(core_registry._iter_entry_points("jobtracker.sources")))


if __name__ == "__main__":
    unittest.main()
