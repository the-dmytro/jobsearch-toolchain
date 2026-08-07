from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import MailInbox
from .eml import parse_email_message


class MaildirInbox:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def list_folders(self) -> list[str]:
        if not self.root.exists():
            return []
        folders = [self.root.name]
        for path in sorted(self.root.rglob("cur")):
            if path.parent != self.root and path.parent.name in {"cur", "new", "tmp"}:
                continue
            relative = path.parent.relative_to(self.root.parent if path.parent.parent == self.root else self.root)
            folders.append(str(relative).replace("\\", "/"))
        return sorted(set(folders))

    def resolve_folder(self, provider: str, explicit_folder: str | None = None) -> str:
        if explicit_folder:
            return explicit_folder
        return self.root.name

    def fetch_messages(self, folder: str, since: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        folder_path = self.root if folder == self.root.name else self.root / folder
        messages: list[dict[str, Any]] = []
        for subdir in ("cur", "new"):
            message_dir = folder_path / subdir
            if not message_dir.exists():
                continue
            files = sorted(message_dir.iterdir(), key=lambda path: path.name)
            if limit is not None:
                files = files[-limit:]
            for path in files:
                if not path.is_file():
                    continue
                parsed = parse_email_message(path.read_bytes())
                parsed["maildir_path"] = str(path)
                if not parsed.get("external_id"):
                    parsed["external_id"] = path.name
                messages.append(parsed)
        return messages


class MaildirMailInbox(MaildirInbox, MailInbox):
    pass
