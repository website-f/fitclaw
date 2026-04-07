from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
import socket
from typing import Any

from ai_ops_agent.paths import config_path, ensure_runtime_dirs


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_capabilities(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        return ["shell"]
    values = raw if isinstance(raw, list) else raw.split(",")
    cleaned = [item.strip() for item in values if str(item).strip()]
    return cleaned or ["shell"]


@dataclass(slots=True)
class AgentConfig:
    api_base_url: str = "http://localhost:8000"
    agent_name: str = field(default_factory=socket.gethostname)
    username: str = "agent"
    shared_key: str = "change-me-now"
    capabilities: list[str] = field(default_factory=lambda: ["shell"])
    poll_interval_seconds: float = 10.0
    heartbeat_interval_seconds: float = 30.0
    allow_unassigned: bool = True
    task_timeout_seconds: int = 1800
    auto_start: bool = True
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)

    def normalized(self) -> "AgentConfig":
        self.api_base_url = self.api_base_url.rstrip("/")
        self.agent_name = self.agent_name.strip()
        self.username = self.username.strip() or "agent"
        self.shared_key = self.shared_key.strip()
        self.capabilities = _parse_capabilities(self.capabilities)
        self.updated_at = _utcnow_iso()
        return self

    def validate(self) -> list[str]:
        self.normalized()
        errors: list[str] = []
        if not self.api_base_url.startswith(("http://", "https://")):
            errors.append("Server URL must start with http:// or https://")
        if not self.agent_name:
            errors.append("Agent name is required")
        if not self.shared_key:
            errors.append("Shared key is required")
        if self.poll_interval_seconds <= 0:
            errors.append("Poll interval must be greater than 0")
        if self.heartbeat_interval_seconds <= 0:
            errors.append("Heartbeat interval must be greater than 0")
        if self.task_timeout_seconds <= 0:
            errors.append("Task timeout must be greater than 0")
        return errors

    def to_json_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["capabilities"] = _parse_capabilities(self.capabilities)
        return payload

    def save(self) -> None:
        ensure_runtime_dirs()
        self.normalized()
        with config_path().open("w", encoding="utf-8") as handle:
            json.dump(self.to_json_dict(), handle, indent=2)

    @classmethod
    def load(cls) -> "AgentConfig":
        if config_path().exists():
            with config_path().open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            config = cls(**payload)
        else:
            config = cls.from_environment()
        return config.normalized()

    @classmethod
    def from_environment(cls) -> "AgentConfig":
        return cls(
            api_base_url=os.getenv("AI_OPS_API_BASE_URL", "http://localhost:8000"),
            agent_name=os.getenv("AGENT_NAME", socket.gethostname()),
            username=os.getenv("AGENT_BASIC_AUTH_USERNAME", "agent"),
            shared_key=os.getenv("AGENT_API_SHARED_KEY", "change-me-now"),
            capabilities=_parse_capabilities(os.getenv("AGENT_CAPABILITIES", "shell")),
            poll_interval_seconds=float(os.getenv("AGENT_POLL_INTERVAL_SECONDS", "10")),
            heartbeat_interval_seconds=float(os.getenv("AGENT_HEARTBEAT_INTERVAL_SECONDS", "30")),
            allow_unassigned=_parse_bool(os.getenv("AGENT_ALLOW_UNASSIGNED", "true")),
            task_timeout_seconds=int(os.getenv("AGENT_TASK_TIMEOUT_SECONDS", "1800")),
            auto_start=_parse_bool(os.getenv("AGENT_AUTO_START", "true")),
        ).normalized()

