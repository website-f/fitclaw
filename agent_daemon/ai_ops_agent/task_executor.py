from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Any

from ai_ops_agent.config import AgentConfig


def _detect_execution_mode(description: str, metadata_json: dict[str, Any]) -> tuple[str, str | None]:
    command = metadata_json.get("command")
    execution_mode = str(metadata_json.get("execution_mode", "ack")).strip().lower()
    stripped = description.strip()
    if not command and stripped.lower().startswith("shell:"):
        return "shell", stripped.split(":", 1)[1].strip()
    if not command and stripped.lower().startswith("powershell:"):
        return "powershell", stripped.split(":", 1)[1].strip()
    return execution_mode, command


def _run_shell(command: str, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout_seconds)


def _run_powershell(command: str, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    if platform.system() == "Windows":
        executable = shutil.which("powershell") or "powershell"
    else:
        executable = shutil.which("pwsh")
        if executable is None:
            raise RuntimeError("PowerShell execution requested, but `pwsh` is not installed on this machine.")

    return subprocess.run(
        [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def execute_task(task: dict[str, Any], config: AgentConfig) -> tuple[str, str | None, str | None, dict[str, Any]]:
    description = task.get("description", "").strip()
    metadata_json = task.get("metadata_json", {}) or {}
    execution_mode, command = _detect_execution_mode(description, metadata_json)

    if execution_mode not in {"shell", "powershell"} or not command:
        result_text = (
            f"Task acknowledged by {config.agent_name}.\n"
            f"Title: {task.get('title', '')}\n"
            f"Description: {description}"
        )
        return "completed", result_text, None, {"execution_mode": "ack"}

    try:
        completed = _run_powershell(command, config.task_timeout_seconds) if execution_mode == "powershell" else _run_shell(
            command, config.task_timeout_seconds
        )
    except subprocess.TimeoutExpired as exc:
        return "failed", None, f"Task timed out after {config.task_timeout_seconds}s: {exc}", {
            "execution_mode": execution_mode,
            "command": command,
            "timeout_seconds": config.task_timeout_seconds,
        }
    except Exception as exc:
        return "failed", None, str(exc), {"execution_mode": execution_mode, "command": command}

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode == 0:
        return "completed", stdout or "(command completed with no stdout)", None, {
            "execution_mode": execution_mode,
            "command": command,
            "returncode": completed.returncode,
        }

    return "failed", stdout or None, stderr or f"Command exited with code {completed.returncode}", {
        "execution_mode": execution_mode,
        "command": command,
        "returncode": completed.returncode,
    }

