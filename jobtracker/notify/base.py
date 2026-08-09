from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class RunReport:
    pipeline: str
    run_key: str
    status: str
    summary: str
    subject: str | None = None
    body: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline": self.pipeline,
            "run_key": self.run_key,
            "status": self.status,
            "summary": self.summary,
            "subject": self.subject,
            "body": self.body,
            "metadata": dict(self.metadata),
        }


class Notifier(Protocol):
    slug: str

    def notify(self, report: RunReport) -> dict[str, Any]: ...

    def health(self) -> list[str]: ...
