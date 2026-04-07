from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class MessageAttachment:
    kind: str
    path: str
    caption: str | None = None
    filename: str | None = None

    def resolve_path(self) -> Path | None:
        raw = self.path.strip()
        if not raw:
            return None

        candidates = [Path(raw)]
        normalized = raw.replace("\\", "/")
        repo_root = Path(__file__).resolve().parents[2]
        if normalized.startswith("/data/"):
            candidates.append(repo_root / "data" / normalized.removeprefix("/data/"))
        elif normalized.startswith("data/"):
            candidates.append(repo_root / normalized)

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None


@dataclass(slots=True)
class CommandResult:
    reply: str
    provider: str = "command"
    handled_as_task_command: bool = False
    handled_as_agent_command: bool = False
    attachments: list[MessageAttachment] = field(default_factory=list)
