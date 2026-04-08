from __future__ import annotations

import re
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.agent import Agent, AgentStatus
from app.models.device_command import DeviceCommandStatus
from app.models.task import TaskStatus
from app.services.agent_service import AgentService
from app.services.command_result import CommandResult, MessageAttachment
from app.services.device_control_service import DeviceControlService
from app.services.task_service import TaskService


class AgentCommandService:
    LIST_AGENTS_PATTERN = re.compile(
        r"(?:^|\b)(?:list|show)\s+(?:my\s+)?agents?\b|(?:^|\b)what\s+agents?\s+(?:are|is)\b",
        re.IGNORECASE,
    )
    VERIFY_PATTERN = re.compile(
        r"\bverify\b.*\b(agent|device|pc|computer|status|heartbeat)\b|"
        r"\b(?:is|check|show|confirm|verify)\b.*\b(agent|device|pc|computer)\b.*\b(status|online|installed|connected|alive|active|working|heartbeat)\b|"
        r"\bmy\s+(?:current\s+)?(?:agent|device|pc)\b.*\b(status|online|installed|connected|alive|heartbeat)\b|"
        r"\bstatus\s+(?:for|of)\s+(?:my\s+)?(?:agent|device|pc)\b",
        re.IGNORECASE,
    )
    SCREENSHOT_PATTERN = re.compile(
        r"\b(screenshot|screen\s*shot|screen\s*capture|current\s+screen|capture\s+the\s+screen|capture\s+screen)\b",
        re.IGNORECASE,
    )
    STORAGE_PATTERN = re.compile(
        r"\b(storage|disk\s+usage|disk\s+space|drive\s+space|free\s+space|capacity|available\s+space)\b",
        re.IGNORECASE,
    )
    BIGGEST_FILES_PATTERN = re.compile(
        r"\b(top|largest|biggest)\b.*\b(file|files|folder|folders|directory|directories)\b|"
        r"\bbiggest\b.*\b(file|files|folder|folders|directory|directories)\b",
        re.IGNORECASE,
    )
    PROCESS_PATTERN = re.compile(r"\b(?:list|show)\b.*\bprocess(?:es)?\b", re.IGNORECASE)
    WINDOW_PATTERN = re.compile(r"\b(?:list|show)\b.*\bwindows?\b", re.IGNORECASE)
    OPEN_VSCODE_PATTERN = re.compile(r"^(?:open|launch)\s+(?:vs\s*code|vscode|code)\b", re.IGNORECASE)
    CODEX_PATTERN = re.compile(
        r"\b(?:run|ask|send|use)\b.*\bcodex\b|\binside\s+vscode\s+codex\b|\b(?:run|ask)\s+codex\b",
        re.IGNORECASE,
    )
    ONLINE_ONLY_COMMANDS = {"screenshot", "storage_summary", "disk_usage_scan", "process_list", "window_list", "app_action"}

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
        if cls.STORAGE_PATTERN.search(normalized) or cls.BIGGEST_FILES_PATTERN.search(normalized):
            return cls._handle_storage_inspection(db, user_id, normalized)
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
            prefs = AgentService.get_model_preferences(agent)
            preferred_text = prefs.get("preferred_text")
            preferred_label = (
                f"{preferred_text['provider']} / {preferred_text['model']}" if preferred_text else "default runtime"
            )
            lines.append(
                f"- {agent.name}: {agent.status.value} | last heartbeat {cls._format_timestamp(agent.last_heartbeat_at)} | {platform_name} | text model {preferred_label}"
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
        prefs = AgentService.get_model_preferences(agent)
        preferred_text = prefs.get("preferred_text")
        preferred_vision = prefs.get("preferred_vision")
        allowed_models = prefs.get("allowed_models", [])
        lines = [
            f"Agent `{agent.name}` is `{agent.status.value}`.",
            f"Last heartbeat: {cls._format_timestamp(agent.last_heartbeat_at)}",
            f"Current task: {current_task}",
            f"Platform: {metadata.get('platform', 'unknown')}",
            f"Capabilities: {capability_text}",
        ]
        if preferred_text:
            lines.append(f"Preferred text model: {preferred_text['provider']} / {preferred_text['model']}")
        if preferred_vision:
            lines.append(f"Preferred vision model: {preferred_vision['provider']} / {preferred_vision['model']}")
        if allowed_models:
            lines.append(
                "Allowed models: "
                + ", ".join(f"{item['provider']} / {item['model']}" for item in allowed_models[:8])
            )
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
    def _handle_storage_inspection(cls, db: Session, user_id: str, text: str) -> CommandResult:
        agent, error = cls._resolve_agent(db, text)
        if error:
            return cls._simple_reply(error)
        assert agent is not None

        target_path = cls._extract_storage_path(text)
        top_n = cls._extract_top_count(text, default=10)
        if not cls._agent_supports_capability(agent, "storage"):
            return cls._handle_storage_inspection_fallback(db, user_id, agent, target_path, top_n)

        summary_command, timeout_error = cls._execute_and_wait(
            db=db,
            user_id=user_id,
            agent=agent,
            command_type="storage_summary",
            payload_json={"path": target_path} if target_path else {},
            timeout_seconds=60,
        )
        if timeout_error:
            return cls._simple_reply(timeout_error)
        assert summary_command is not None
        if summary_command.status == DeviceCommandStatus.failed:
            if cls._should_use_storage_fallback(summary_command.error_text):
                return cls._handle_storage_inspection_fallback(db, user_id, agent, target_path, top_n)
            return cls._simple_reply(
                f"Storage inspection failed on `{agent.name}`: {summary_command.error_text or 'unknown error'}"
            )

        scan_command, timeout_error = cls._execute_and_wait(
            db=db,
            user_id=user_id,
            agent=agent,
            command_type="disk_usage_scan",
            payload_json={"path": target_path, "top_n": top_n},
            timeout_seconds=600,
        )
        if timeout_error:
            return cls._simple_reply(timeout_error)
        assert scan_command is not None
        if scan_command.status == DeviceCommandStatus.failed:
            if cls._should_use_storage_fallback(scan_command.error_text):
                return cls._handle_storage_inspection_fallback(db, user_id, agent, target_path, top_n)
            return cls._simple_reply(
                f"Disk scan failed on `{agent.name}`: {scan_command.error_text or 'unknown error'}"
            )

        summary = summary_command.result_json or {}
        usage = summary.get("target_usage", {})
        partitions = list(summary.get("partitions", []))[:4]
        scan = scan_command.result_json or {}
        top_files = list(scan.get("top_files", []))[:top_n]
        top_folders = list(scan.get("top_folders", []))[:top_n]

        lines = [
            f"Storage inspection for `{agent.name}` completed.",
            f"Target: {summary.get('path') or (target_path or 'the main storage path')}",
            (
                "Usage: "
                f"{cls._format_bytes(usage.get('used_bytes'))} used / "
                f"{cls._format_bytes(usage.get('total_bytes'))} total / "
                f"{cls._format_bytes(usage.get('free_bytes'))} free "
                f"({usage.get('percent', '?')}%)"
            ),
        ]

        if partitions:
            lines.extend(["", "Top mounted volumes:"])
            for item in partitions:
                lines.append(
                    f"- {item.get('mountpoint') or item.get('device')}: "
                    f"{cls._format_bytes(item.get('used_bytes'))} used / "
                    f"{cls._format_bytes(item.get('total_bytes'))} total "
                    f"({item.get('percent', '?')}%)"
                )

        lines.extend(
            [
                "",
                f"Scan summary: {scan.get('scanned_files', 0)} files, {scan.get('scanned_dirs', 0)} folders, "
                f"{scan.get('skipped_entries', 0)} skipped, about {scan.get('estimated_total_human') or cls._format_bytes(scan.get('estimated_total_bytes'))} scanned.",
            ]
        )

        if top_folders:
            lines.extend(["", f"Top {min(top_n, len(top_folders))} largest folders:"])
            for item in top_folders:
                lines.append(f"- {item.get('path')}: {item.get('size_human') or cls._format_bytes(item.get('size_bytes'))}")

        if top_files:
            lines.extend(["", f"Top {min(top_n, len(top_files))} largest files:"])
            for item in top_files:
                lines.append(f"- {item.get('path')}: {item.get('size_human') or cls._format_bytes(item.get('size_bytes'))}")

        return CommandResult(
            reply="\n".join(lines),
            provider="agent-command",
            handled_as_agent_command=True,
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
    def _execute_task_and_wait(
        cls,
        db: Session,
        user_id: str,
        agent: Agent,
        description: str,
        timeout_seconds: int,
        title: str,
        metadata_json: dict | None = None,
    ):
        task = TaskService.create_task(
            db=db,
            title=title,
            description=description,
            assigned_agent_name=agent.name,
            source="telegram",
            command_type="compatibility-task",
            created_by_user_id=user_id,
            metadata_json=metadata_json or {},
        )

        deadline = time.monotonic() + max(timeout_seconds, 5)
        while time.monotonic() < deadline:
            db.expire_all()
            current = TaskService.get_task_by_task_id(db, task.task_id)
            if current and current.status in {TaskStatus.completed, TaskStatus.failed}:
                return current, None
            time.sleep(1.0)

        db.expire_all()
        current = TaskService.get_task_by_task_id(db, task.task_id)
        if current and current.status in {TaskStatus.completed, TaskStatus.failed}:
            return current, None
        return current, f"Sent storage task `{task.task_id}` to `{agent.name}`, but it is still running. Try again shortly."

    @classmethod
    def _handle_storage_inspection_fallback(
        cls,
        db: Session,
        user_id: str,
        agent: Agent,
        target_path: str | None,
        top_n: int,
    ) -> CommandResult:
        script, execution_mode, timeout_seconds = cls._build_storage_fallback_task(agent, target_path, top_n)
        if not script:
            return cls._simple_reply(
                f"`{agent.name}` is on an older agent build that does not support direct storage inspection yet. "
                "Please reinstall the latest agent build on that device."
            )

        prefix = "powershell" if execution_mode == "powershell" else "shell"
        description = f"{prefix}:\n{script}"
        task, timeout_error = cls._execute_task_and_wait(
            db=db,
            user_id=user_id,
            agent=agent,
            description=description,
            timeout_seconds=timeout_seconds,
            title="Compatibility storage inspection",
            metadata_json={"execution_mode": execution_mode, "command": script, "hidden_window": True},
        )
        if timeout_error:
            return cls._simple_reply(timeout_error)
        assert task is not None

        if task.status == TaskStatus.failed:
            return cls._simple_reply(
                f"Storage inspection fallback failed on `{agent.name}`: {task.error_text or 'unknown error'}"
            )

        result_text = (task.result_text or "").strip()
        if not result_text:
            result_text = f"Storage inspection completed on `{agent.name}`, but the legacy agent returned no output."
        return CommandResult(
            reply=result_text,
            provider="agent-command",
            handled_as_agent_command=True,
        )

    @classmethod
    def _build_storage_fallback_task(
        cls,
        agent: Agent,
        target_path: str | None,
        top_n: int,
    ) -> tuple[str | None, str, int]:
        platform_name = str((agent.metadata_json or {}).get("platform", "")).lower()
        if "windows" in platform_name:
            return cls._build_windows_storage_script(agent.name, target_path, top_n), "powershell", 900
        return None, "shell", 600

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
    def _extract_storage_path(text: str) -> str | None:
        match = re.search(
            r"\b(?:in|at|under|from)\s+((?:[A-Za-z]:\\|/).+?)(?=\s+(?:and|top|largest|biggest|show|list|check)\b|$)",
            text,
            re.IGNORECASE,
        )
        if not match:
            return None
        path = match.group(1).strip().strip("\"'")
        return path or None

    @staticmethod
    def _extract_top_count(text: str, default: int = 10) -> int:
        match = re.search(r"\btop\s+(\d{1,2})\b", text, re.IGNORECASE)
        if not match:
            return default
        value = int(match.group(1))
        return max(1, min(value, 25))

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
    def _agent_supports_capability(agent: Agent, capability: str) -> bool:
        capabilities = {str(item).strip().lower() for item in (agent.capabilities_json or [])}
        return capability.strip().lower() in capabilities

    @staticmethod
    def _should_use_storage_fallback(error_text: str | None) -> bool:
        lowered = str(error_text or "").strip().lower()
        return "unsupported control command" in lowered or "storage_summary" in lowered or "disk_usage_scan" in lowered

    @staticmethod
    def _escape_powershell_single_quoted(value: str) -> str:
        return value.replace("'", "''")

    @classmethod
    def _build_windows_storage_script(cls, agent_name: str, target_path: str | None, top_n: int) -> str:
        safe_agent_name = cls._escape_powershell_single_quoted(agent_name)
        if target_path:
            target_assignment = f"$TargetPath = '{cls._escape_powershell_single_quoted(target_path)}'"
        else:
            target_assignment = '$TargetPath = if ($env:SystemDrive) { "$($env:SystemDrive)\\" } else { "C:\\" }'

        return f"""
$ErrorActionPreference = 'Stop'

function Format-Bytes([Int64]$Bytes) {{
    if ($Bytes -lt 1KB) {{ return "$Bytes B" }}
    if ($Bytes -lt 1MB) {{ return ('{{0:N1}} KB' -f ($Bytes / 1KB)) }}
    if ($Bytes -lt 1GB) {{ return ('{{0:N1}} MB' -f ($Bytes / 1MB)) }}
    if ($Bytes -lt 1TB) {{ return ('{{0:N1}} GB' -f ($Bytes / 1GB)) }}
    return ('{{0:N1}} TB' -f ($Bytes / 1TB))
}}

{target_assignment}
$TopN = {top_n}

if (-not (Test-Path -LiteralPath $TargetPath)) {{
    throw "Path not found: $TargetPath"
}}

$ResolvedPath = (Resolve-Path -LiteralPath $TargetPath).Path
$RootTrimmed = $ResolvedPath.TrimEnd('\\')
$Lines = [System.Collections.Generic.List[string]]::new()
$DriveRoot = [System.IO.Path]::GetPathRoot($ResolvedPath)
$DriveInfo = $null

if ($DriveRoot) {{
    $DeviceId = $DriveRoot.TrimEnd('\\')
    $DriveInfo = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='$DeviceId'" -ErrorAction SilentlyContinue
}}

$Lines.Add("Storage inspection for {safe_agent_name} completed.")
$Lines.Add("Target: $ResolvedPath")

if ($DriveInfo -and $DriveInfo.Size) {{
    $TotalBytes = [Int64]$DriveInfo.Size
    $FreeBytes = [Int64]$DriveInfo.FreeSpace
    $UsedBytes = $TotalBytes - $FreeBytes
    $Percent = if ($TotalBytes -gt 0) {{ [Math]::Round(($UsedBytes / $TotalBytes) * 100, 1) }} else {{ 0 }}
    $Lines.Add("Usage: $(Format-Bytes $UsedBytes) used / $(Format-Bytes $TotalBytes) total / $(Format-Bytes $FreeBytes) free ($Percent%)")
}}

$AllDirs = @(Get-ChildItem -LiteralPath $ResolvedPath -Recurse -Force -Directory -ErrorAction SilentlyContinue)
$AllFiles = @(Get-ChildItem -LiteralPath $ResolvedPath -Recurse -Force -File -ErrorAction SilentlyContinue)
$DirSizes = @{{}}
$ScannedFiles = 0
$SkippedEntries = 0

foreach ($File in $AllFiles) {{
    try {{
        $Size = [Int64]$File.Length
        $ScannedFiles += 1
        $Current = $File.DirectoryName
        while ($Current) {{
            if (-not $Current.StartsWith($RootTrimmed, [System.StringComparison]::OrdinalIgnoreCase)) {{
                break
            }}
            if ($DirSizes.ContainsKey($Current)) {{
                $DirSizes[$Current] += $Size
            }} else {{
                $DirSizes[$Current] = $Size
            }}
            if ([string]::Equals($Current.TrimEnd('\\'), $RootTrimmed, [System.StringComparison]::OrdinalIgnoreCase)) {{
                break
            }}
            $Parent = Split-Path -LiteralPath $Current -Parent
            if (-not $Parent -or [string]::Equals($Parent, $Current, [System.StringComparison]::OrdinalIgnoreCase)) {{
                break
            }}
            $Current = $Parent
        }}
    }} catch {{
        $SkippedEntries += 1
    }}
}}

$TopFolders = @(
    $DirSizes.GetEnumerator() |
    Where-Object {{ -not [string]::Equals($_.Key.TrimEnd('\\'), $RootTrimmed, [System.StringComparison]::OrdinalIgnoreCase) }} |
    Sort-Object Value -Descending |
    Select-Object -First $TopN
)
$TopFiles = @($AllFiles | Sort-Object Length -Descending | Select-Object -First $TopN)

$Lines.Add("")
$Lines.Add("Scan summary: $ScannedFiles files, $($AllDirs.Count) folders, $SkippedEntries skipped.")

if ($TopFolders.Count -gt 0) {{
    $Lines.Add("")
    $Lines.Add("Top $($TopFolders.Count) largest folders:")
    foreach ($Folder in $TopFolders) {{
        $Lines.Add("- $($Folder.Key): $(Format-Bytes ([Int64]$Folder.Value))")
    }}
}}

if ($TopFiles.Count -gt 0) {{
    $Lines.Add("")
    $Lines.Add("Top $($TopFiles.Count) largest files:")
    foreach ($File in $TopFiles) {{
        $Lines.Add("- $($File.FullName): $(Format-Bytes ([Int64]$File.Length))")
    }}
}}

$Lines -join [Environment]::NewLine
""".strip()

    @staticmethod
    def _simple_reply(reply: str) -> CommandResult:
        return CommandResult(
            reply=reply,
            provider="agent-command",
            handled_as_agent_command=True,
        )
