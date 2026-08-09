from __future__ import annotations

from typing import Any

from jobtracker.core.models import Candidate, ConnectorBuildContext
from jobtracker.mail.base import OutgoingMessage, SendReceipt
from jobtracker.store.generic.memory import MemoryJobStore


class FixtureSource:
    def __init__(self, slug: str) -> None:
        self.slug = slug

    def discover(self, ctx):
        candidate = Candidate(
            external_id="fixture-1",
            title="Software Engineer",
            source_url="https://jobs.example.invalid/fixture-1",
            apply_url="https://jobs.example.invalid/fixture-1",
            company="Example Company",
        )
        ctx.metrics.jobs_discovered = 1
        ctx.metrics.jobs_emitted = 1
        return [candidate], "completed", []

    def health(self, ctx):
        return []


class FixtureParser:
    def matches(self, message: dict[str, Any]) -> bool:
        return "fixture alert" in str(message.get("subject") or "").lower()

    def parse(self, message: dict[str, Any]) -> dict[str, Any] | None:
        return {"provider_slug": "fixture", "links": list(message.get("links") or [])} if self.matches(message) else None


class FixtureInbox:
    def list_folders(self):
        return ["fixture"]

    def resolve_folder(self, provider, explicit_folder=None):
        return explicit_folder or "fixture"

    def fetch_messages(self, folder, since=None, limit=None):
        messages = [{"external_id": "fixture-message-1", "subject": "Fixture alert"}]
        return messages[:limit] if limit is not None else messages


class FixtureSender:
    def send(self, message: OutgoingMessage) -> SendReceipt:
        return SendReceipt(sent=True, recipient=message.recipient, subject=message.subject)


class FixtureNotifier:
    slug = "fixture_notifier"

    def notify(self, report):
        return {"sent": True, "run_key": report.run_key}

    def health(self):
        return []


def build_source(context: ConnectorBuildContext):
    return FixtureSource(context.slug)


def build_parser(context: ConnectorBuildContext):
    return FixtureParser()


def build_inbox(context: ConnectorBuildContext):
    return FixtureInbox()


def build_sender(context: ConnectorBuildContext):
    return FixtureSender()


def build_store(context: ConnectorBuildContext):
    return MemoryJobStore()


def build_notifier(context: ConnectorBuildContext):
    notifier = FixtureNotifier()
    notifier.slug = context.slug
    return notifier
