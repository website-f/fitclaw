from __future__ import annotations

import re
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.agent import Agent, AgentStatus
from app.models.device_command import DeviceCommandStatus
from app.services.agent_service import AgentService
from app.services.command_result import CommandResult, MessageAttachment
from app.services.device_control_service import DeviceControlService


class AgentCommandService:
    LIST_AGENTS_PATTERN = re.compile(
        r"(?:^|\b)(?:list|show)\s+(?:my\s+)?agents?\b|(?:^|\b)what\s+agents?\s+(?:are|is)\b",
        re.IGNORECASE,
    )
    VERIFY_PATTERN = re.compile(
        r"\bverify\b.*\b(agent|device|pc)\b|\b(?:is|check|show)\b.*\b(agent|device|pc)\b.*\b(online|installed|connected|alive)\b",
        re.IGNORECASE,
    )
    SCREENSHOT_PATTERN = re.compile(
        r"\b(screenshot|screen\s*shot|screen\s*capture|current\s+screen|capture\s+the\s+screen|capture\s+screen)\b",
        re.IGNORECASE,
    )
    PROCESS_PATTERN = re.compile(r"\b(?:list|show)\b.*\bprocess(?:es)?\b", re.IGNORECASE)
    WINDOW_PATTERN = re.compile(r"\b(?:list|show)\b.*\bwindows?\b", re.IGNORECASE)
    OPEN_VSCODE_PATTERN = re.compile(r"^(?:open|launch)\s+(?:vs\s*code|vscode|code)\b", re.IGNORECASE)
    CODEX_PATTERN = re.compile(
        r"\b(?:run|ask|send|use)\b.*\bcodex\b|\binside\s+vscode\s+codex\b|\b(?:run|ask)\s+codex\b",
        re.IGNORECASE,
    )
    ONLINE_ONLY_COMMANDS = {"screenshot", "process_list", "window_list", "app_action"}

    @classmethod
    def try_handle(cls, db: Session, user_id: str, text: str) -> CommandResult | None:
        normalized = text.strip()
        if not normalized:
            return None

        AgentService.mark_stale_agents(db)

        if cls.LIST_AGENTS_PATTERN.search(normalized):
            return cls._handle_list_agents(db)
        if cls.VERIFY_PATTERN.search(normalized):
            return cls._handle_verify_agent(db, normalized)
        if cls.SCREENSHOT_PATTERN.search(normalized):
            return cls._handle_screenshot(db, user_id, normalized)
        if cls.PROCESS_PATTERN.search(normalized):
            return cls._handle_process_list(db, user_id, normalized)
        if cls.WINDOW_PATTERN.search(normalized):
            return cls._handle_window_list(db, user_id, normalized)
        if cls.OPEN_VSCODE_PATTERN.search(normalized):
            return cls._handle_open_vscode(db, user_id, normalized)
        if cls.CODEX_PATTERN.search(normalized):
            return cls._handle_codex(db, user_id, normalized)

        return None

    @classmethod
    def _handle_list_agents(cls, db: Session) -> CommandResult:
        agents = AgentService.list_agents(db)
        if not agents:
            return CommandResult(
                reply="No agents are registered yet. Install the agent on a device first, then wait for it to heartbeat.",
                provider="agent-command",
                handled_as_agent_command=True,
            )

        lines = ["Agents:"]
        for agent in agents:
            platform_name = str(agent.metadata_json.get("platform", "unknown"))
            lines.append(
                f"- {agent.name}: {agent.status.value} | last heartbeat {cls._format_timestamp(agent.last_heartbeat_at)} | {platform_name}"
            )
        return CommandResult(
            reply="\n".join(lines),
            provider="agent-command",
            handled_as_agent_command=True,
        )

    @classmethod
    def _handle_verify_agent(cls, db: Session, text: str) -> CommandResult:
        agent, error = cls._resolve_agent(db, text, require_specific=False)
        if error:
            return cls._simple_reply(error)
        if agent is None:
            return cls._simple_reply("I could not find any registered agents to verify yet.")

        capabilities = agent.capabilities_json or []
        capability_text = ", ".join(capabilities[:10]) if capabilities else "none reported yet"
        metadata = agent.metadata_json or {}
        current_task = agent.current_task_id or "idle"
        lines = [
            f"Agent `{agent.name}` is `{agent.status.value}`.",
            f"Last heartbeat: {cls._format_timestamp(agent.last_heartbeat_at)}",
            f"Current task: {current_task}",
            f"Platform: {metadata.get('platform', 'unknown')}",
            f"Capabilities: {capability_text}",
        ]
        return CommandResult(
            reply="\n".join(lines),
            provider="agent-command",
            handled_as_agent_command=True,
        )

    @classmethod
    def _handle_screenshot(cls, db: Session, user_id: str, text: str) -> CommandResult:
        agent, error = cls._resolve_agent(db, text)
        if error:
            return cls._simple_reply(error)
        assert agent is not None

        command, timeout_error = cls._execute_and_wait(
            db=db,
            user_id=user_id,
            agent=agent,
            command_type="screenshot",
            payload_json={"format": "jpeg", "quality": 78, "max_width": 1600},
            timeout_seconds=45,
        )
        if timeout_error:
            return cls._simple_reply(timeout_error)
        assert command is not None

        if command.status == DeviceCommandStatus.failed:
            return cls._simple_reply(f"Screenshot failed on `{agent.name}`: {command.error_text or 'unknown error'}")

        result = command.result_json or {}
        screen = result.get("screen_size", {})
        reply = (
            f"Screenshot captured from `{agent.name}`.\n"
            f"Screen: {screen.get('width', '?')}x{screen.get('height', '?')}\n"
            f"Captured: {result.get('captured_at', 'just now')}"
        )
        attachments: list[MessageAttachment] = []
        if command.artifact_path:
            attachments.append(
                MessageAttachment(
                    kind="photo",
                    path=command.artifact_path,
                    caption=f"{agent.name} screenshot",
                    filename=Path(command.artifact_path).name,
                )
            )

        return CommandResult(
            reply=reply,
            provider="agent-command",
            handled_as_agent_command=True,
            attachments=attachments,
        )

    @classmethod
    def _handle_process_list(cls, db: Session, user_id: str, text: str) -> CommandResult:
        agent, error = cls._resolve_agent(db, text)
        if error:
            return cls._simple_reply(error)
        assert agent is not None

        command, timeout_error = cls._execute_and_wait(
            db=db,
            user_id=user_id,
            agent=agent,
            command_type="process_list",
            payload_json={},
            timeout_seconds=40,
        )
        if timeout_error:
            return cls._simple_reply(timeout_error)
        assert command is not None

        if command.status == DeviceCommandStatus.failed:
            return cls._simple_reply(f"Process listing failed on `{agent.name}`: {command.error_text or 'unknown error'}")

        processes = list((command.result_json or {}).get("processes", []))[:12]
        if not processes:
            return cls._simple_reply(f"`{agent.name}` returned no running processes.")

        lines = [f"Top processes on `{agent.name}`:"]
        for item in processes:
            lines.append(
                f"- PID {item.get('pid')}: {item.get('name') or 'unknown'} | CPU {item.get('cpu_percent') or 0}% | RAM {cls._format_bytes(item.get('rss_bytes'))}"
            )
        return CommandResult(
            reply="\n".join(lines),
            provider="agent-command",
            handled_as_agent_command=True,
        )

    @classmethod
    def _handle_window_list(cls, db: Session, user_id: str, text: str) -> CommandResult:
        agent, error = cls._resolve_agent(db, text)
        if error:
            return cls._simple_reply(error)
        assert agent is not None

        command, timeout_error = cls._execute_and_wait(
            db=db,
            user_id=user_id,
            agent=agent,
            command_type="window_list",
            payload_json={},
            timeout_seconds=40,
        )
        if timeout_error:
            return cls._simple_reply(timeout_error)
        assert command is not None

        if command.status == DeviceCommandStatus.failed:
            return cls._simple_reply(f"Window listing failed on `{agent.name}`: {command.error_text or 'unknown error'}")

        windows = list((command.result_json or {}).get("windows", []))[:15]
        if not windows:
            return cls._simple_reply(f"I did not find visible windows on `{agent.name}`.")

        lines = [f"Visible windows on `{agent.name}`:"]
        for item in windows:
            title = str(item.get("title", "")).strip() or "(untitled)"
            lines.append(f"- {title} ({item.get('width', '?')}x{item.get('height', '?')})")
        return CommandResult(
            reply="\n".join(lines),
            provider="agent-command",
            handled_as_agent_command=True,
        )

    @classmethod
    def _handle_open_vscode(cls, db: Session, user_id: str, text: str) -> CommandResult:
        agent, error = cls._resolve_agent(db, text)
        if error:
            return cls._simple_reply(error)
        assert agent is not None

        workspace_path = cls._extract_workspace_path(text)
        payload = {"action": "vscode_open_path"}
        if workspace_path:
            payload["path"] = workspace_path

        command, timeout_error = cls._execute_and_wait(
            db=db,
            user_id=user_id,
            agent=agent,
            command_type="app_action",
            payload_json=payload,
            timeout_seconds=45,
        )
        if timeout_error:
            return cls._simple_reply(timeout_error)
        assert command is not None

        if command.status == DeviceCommandStatus.failed:
            return cls._simple_reply(f"VS Code launch failed on `{agent.name}`: {command.error_text or 'unknown error'}")

        target = workspace_path or "a new VS Code window"
        return CommandResult(
            reply=f"VS Code launched on `{agent.name}` for `{target}`.",
            provider="agent-command",
            handled_as_agent_command=True,
        )

    @classmethod
    def _handle_codex(cls, db: Session, user_id: str, text: str) -> CommandResult:
        agent, error = cls._resolve_agent(db, text)
        if error:
            return cls._simple_reply(error)
        assert agent is not None

        prompt = cls._extract_codex_prompt(text)
        if not prompt:
            return cls._simple_reply(
                "I need a Codex prompt. Example: `run this prompt inside vscode codex on office-pc in C:\\projects\\repo: fix the failing tests`"
            )

        workspace_path = cls._extract_workspace_path(text)
        payload = {
            "action": "codex_exec",
            "prompt": prompt,
            "workspace_path": workspace_path,
            "open_in_vscode": True,
            "timeout_seconds": 900,
        }

        command, timeout_error = cls._execute_and_wait(
            db=db,
            user_id=user_id,
            agent=agent,
            command_type="app_action",
            payload_json=payload,
            timeout_seconds=920,
        )
        if timeout_error:
            return cls._simple_reply(timeout_error)
        assert command is not None

        if command.status == DeviceCommandStatus.failed:
            return cls._simple_reply(f"Codex execution failed on `{agent.name}`: {command.error_text or 'unknown error'}")

        result = command.result_json or {}
        excerpt = str(result.get("last_message_excerpt") or "").strip()
        workspace_label = workspace_path or "the current working directory"
        reply_lines = [
            f"Codex finished on `{agent.name}`.",
            f"Workspace: {workspace_label}",
        ]
        if excerpt:
            reply_lines.extend(["", excerpt])

        attachments: list[MessageAttachment] = []
        if command.artifact_path:
            attachments.append(
                MessageAttachment(
                    kind="document",
                    path=command.artifact_path,
                    caption=f"Codex output from {agent.name}",
                    filename=Path(command.artifact_path).name,
                )
            )

        return CommandResult(
            reply="\n".join(reply_lines),
            provider="agent-command",
            handled_as_agent_command=True,
            attachments=attachments,
        )

    @classmethod
    def _execute_and_wait(
        cls,
        db: Session,
        user_id: str,
        agent: Agent,
        command_type: str,
        payload_json: dict,
        timeout_seconds: int,
    ):
        if command_type in cls.ONLINE_ONLY_COMMANDS and agent.status != AgentStatus.online:
            return None, (
                f"`{agent.name}` is currently `{agent.status.value}`. Open the agent app on that device and wait for the next heartbeat."
            )

        command = DeviceControlService.create_command(
            db=db,
            agent_name=agent.name,
            command_type=command_type,
            payload_json=payload_json,
            source="telegram",
            created_by_user_id=user_id,
        )

        deadline = time.monotonic() + max(timeout_seconds, 5)
        while time.monotonic() < deadline:
            db.expire_all()
            current = DeviceControlService.get_command(db, command.command_id)
            if current and current.status in {DeviceCommandStatus.completed, DeviceCommandStatus.failed}:
                return current, None
            time.sleep(0.75)

        db.expire_all()
        current = DeviceControlService.get_command(db, command.command_id)
        if current and current.status in {DeviceCommandStatus.completed, DeviceCommandStatus.failed}:
            return current, None
        return current, f"Sent command `{command.command_id}` to `{agent.name}`, but it is still pending. Try again in a few seconds."

    @classmethod
    def _resolve_agent(cls, db: Session, text: str, require_specific: bool = True) -> tuple[Agent | None, str | None]:
        agents = AgentService.list_agents(db)
        if not agents:
            return None, "No agents are registered yet."

        matches = cls._match_agents_in_text(text, agents)
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            names = ", ".join(agent.name for agent in matches)
            return None, f"I found multiple matching agents in that request: {names}. Please name one agent explicitly."

        online_agents = [agent for agent in agents if agent.status == AgentStatus.online]
        if len(online_agents) == 1:
            return online_agents[0], None
        if not require_specific and len(agents) == 1:
            return agents[0], None
        if len(agents) == 1:
            return agents[0], None

        names = ", ".join(agent.name for agent in agents)
        return None, f"I found multiple agents: {names}. Please include the target agent name in your message."

    @staticmethod
    def _match_agents_in_text(text: str, agents: list[Agent]) -> list[Agent]:
        text_lower = text.lower()
        normalized_text = AgentCommandService._normalize_label(text)
        matches: list[Agent] = []

        for agent in agents:
            name = agent.name
            if re.search(rf"(?<![\w.-]){re.escape(name)}(?![\w.-])", text, re.IGNORECASE):
                matches.append(agent)
                continue
            if AgentCommandService._normalize_label(name) in normalized_text:
                matches.append(agent)
                continue
            name_words = name.replace("-", " ").replace("_", " ").replace(".", " ").lower()
            if name_words in text_lower:
                matches.append(agent)

        deduped: dict[str, Agent] = {}
        for agent in matches:
            deduped[agent.name] = agent
        return list(deduped.values())

    @staticmethod
    def _extract_workspace_path(text: str) -> str | None:
        match = re.search(r"\b(?:in|at)\s+((?:[A-Za-z]:\\|/).+?)(?=\s*:\s*|$)", text, re.IGNORECASE)
        if not match:
            return None
        path = match.group(1).strip().strip("\"'")
        return path or None

    @staticmethod
    def _extract_codex_prompt(text: str) -> str | None:
        colon_with_space = re.search(r":\s+(.+)$", text)
        if colon_with_space:
            prompt = colon_with_space.group(1).strip()
            return prompt or None

        quoted = re.search(r"[\"“](.+)[\"”]\s*$", text)
        if quoted:
            prompt = quoted.group(1).strip()
            return prompt or None

        return None

    @staticmethod
    def _format_timestamp(value) -> str:
        if value is None:
            return "unknown"
        try:
            return value.isoformat()
        except AttributeError:
            return str(value)

    @staticmethod
    def _format_bytes(value: int | None) -> str:
        if not value:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(value)
        for unit in units:
            if size < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{value} B"

    @staticmethod
    def _normalize_label(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.lower())

    @staticmethod
    def _simple_reply(reply: str) -> CommandResult:
        return CommandResult(
            reply=reply,
            provider="agent-command",
            handled_as_agent_command=True,
        )
