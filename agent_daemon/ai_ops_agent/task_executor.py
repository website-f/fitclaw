from __future__ import annotations

import base64
import json
import platform
import shutil
import subprocess
from typing import Any

from ai_ops_agent.config import AgentConfig
from ai_ops_agent.control_actions import execute_control_command


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
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if platform.system() == "Windows" else 0
    return subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        creationflags=creationflags,
    )


def _run_powershell(command: str, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    if platform.system() == "Windows":
        executable = shutil.which("powershell") or "powershell"
        encoded_command = base64.b64encode(command.encode("utf-16le")).decode("ascii")
        args = [
            executable,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-EncodedCommand",
            encoded_command,
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        executable = shutil.which("pwsh")
        if executable is None:
            raise RuntimeError("PowerShell execution requested, but `pwsh` is not installed on this machine.")
        encoded_command = base64.b64encode(command.encode("utf-16le")).decode("ascii")
        args = [
            executable,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded_command,
        ]
        creationflags = 0

    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        creationflags=creationflags,
    )


def _summarize_device_result(command_type: str, payload: dict[str, Any], result_json: dict[str, Any]) -> str:
    if command_type == "browser_crawl":
        lines = [f"Crawled {result_json.get('final_url') or payload.get('url') or 'the requested website'}."]
        title = str(result_json.get("title", "")).strip()
        if title:
            lines.append(f"Title: {title}")
        meta_description = str(result_json.get("meta_description", "")).strip()
        if meta_description:
            lines.append(f"Summary: {meta_description}")
        excerpt = str(result_json.get("text_excerpt", "")).strip()
        if excerpt:
            lines.extend(["", excerpt])
        links = list(result_json.get("top_links") or [])
        if links:
            lines.extend(["", "Useful links:"])
            for item in links[:5]:
                label = str(item.get("text", "")).strip() or str(item.get("url", "")).strip()
                url = str(item.get("url", "")).strip()
                if url:
                    lines.append(f"- {label} -> {url}")
        return "\n".join(lines)

    if command_type == "app_action" and str(payload.get("action", "")).strip().lower() == "browser_open_url":
        goal = str(payload.get("goal", "")).strip()
        lines = [f"Opened {payload.get('url') or 'the requested URL'} in the browser."]
        if goal:
            lines.append(f"Goal: {goal}")
        return "\n".join(lines)

    rendered = json.dumps(result_json, ensure_ascii=True, indent=2)
    return rendered[:2000] if len(rendered) > 2000 else rendered


def _execute_device_command_proxy(metadata_json: dict[str, Any], config: AgentConfig) -> tuple[str, str | None, str | None, dict[str, Any]]:
    device_command_type = str(metadata_json.get("device_command_type", "")).strip()
    payload_json = metadata_json.get("device_payload_json", {}) or {}
    if not device_command_type:
        return "failed", None, "No device command type was provided for this automation task.", {
            "execution_mode": "device_command_proxy",
        }

    status, result_json, error_text = execute_control_command(
        {"command_type": device_command_type, "payload_json": payload_json},
        config,
    )
    metadata = {
        "execution_mode": "device_command_proxy",
        "device_command_type": device_command_type,
        "device_payload_json": payload_json,
        "device_result_json": result_json,
    }
    if status != "completed":
        return "failed", None, error_text or f"{device_command_type} failed.", metadata

    result_text = _summarize_device_result(device_command_type, payload_json, result_json or {})
    return "completed", result_text, None, metadata


def execute_task(task: dict[str, Any], config: AgentConfig) -> tuple[str, str | None, str | None, dict[str, Any]]:
    description = task.get("description", "").strip()
    metadata_json = task.get("metadata_json", {}) or {}
    execution_mode, command = _detect_execution_mode(description, metadata_json)

    if execution_mode == "device_command_proxy":
        return _execute_device_command_proxy(metadata_json, config)

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
