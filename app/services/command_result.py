from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass(slots=True)
class MessageAttachment:
    kind: str
    path: str
    caption: str | None = None
    filename: str | None = None
    explicit_public_url: str | None = None
    asset_id: str | None = None

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

    def public_url(self) -> str | None:
        if self.explicit_public_url:
            return self.explicit_public_url

        filename = (self.filename or Path(self.path).name).strip()
        if not filename:
            return None

        match = re.match(r"^(cmd_[a-z0-9]+)\.[A-Za-z0-9]+$", filename, re.IGNORECASE)
        if not match:
            return None

        return f"/api/v1/control/commands/{match.group(1)}/artifact"

    def to_metadata(self) -> dict[str, str]:
        data = {
            "kind": self.kind,
            "path": self.path,
            "caption": self.caption or "",
            "filename": self.filename or "",
        }
        if self.asset_id:
            data["asset_id"] = self.asset_id
        public_url = self.public_url()
        if public_url:
            data["public_url"] = public_url
        return data


@dataclass(slots=True)
class CommandResult:
    reply: str
    provider: str = "command"
    handled_as_task_command: bool = False
    handled_as_agent_command: bool = False
    attachments: list[MessageAttachment] = field(default_factory=list)
