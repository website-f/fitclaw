from __future__ import annotations

import base64
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from typing import Any
import webbrowser

import psutil

from ai_ops_agent.config import AgentConfig


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pyautogui():
    try:
        import pyautogui
    except Exception as exc:
        raise RuntimeError(
            "Mouse and keyboard automation is unavailable because PyAutoGUI could not be loaded. "
            "Reinstall the latest agent build on this device."
        ) from exc

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
    return pyautogui


def _has_pyautogui() -> bool:
    try:
        _pyautogui()
    except Exception:
        return False
    return True


def _image_grab():
    try:
        from PIL import ImageGrab
    except Exception as exc:
        raise RuntimeError(
            "Screenshot capture is unavailable because Pillow ImageGrab could not be loaded. "
            "Reinstall the latest agent build on this device."
        ) from exc
    return ImageGrab


def _has_screenshot_backend() -> bool:
    try:
        _image_grab()
    except Exception:
        return False
    return True


def _load_windows_module():
    try:
        import pygetwindow as gw
    except Exception:
        return None
    return gw


def _bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _truncate_text(value: str, max_chars: int) -> str:
    text = value.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _find_vscode_cli() -> str | None:
    return shutil.which("code") or shutil.which("code-insiders")


def _find_codex_cli() -> str | None:
    return shutil.which("codex")


def available_capabilities(config: AgentConfig) -> list[str]:
    capabilities = set(config.capabilities or [])
    capabilities.update({"shell", "file_system", "processes"})
    if _has_screenshot_backend():
        capabilities.add("screenshot")
    if _has_pyautogui():
        capabilities.add("mouse_keyboard")
    if _load_windows_module() is not None:
        capabilities.add("windows")
    if _find_vscode_cli():
        capabilities.add("vscode")
    if _find_codex_cli():
        capabilities.add("codex")
    return sorted(capabilities)


def _screenshot(payload: dict[str, Any]) -> dict[str, Any]:
    image_grab = _image_grab()
    try:
        image = image_grab.grab(all_screens=True)
    except TypeError:
        image = image_grab.grab()
    if image.mode not in {"RGB", "RGBA"}:
        image = image.convert("RGB")
    screen_width, screen_height = image.size

    max_width = int(payload.get("max_width", 1440))
    if max_width > 0 and image.width > max_width:
        ratio = max_width / image.width
        image = image.resize((max_width, max(1, int(image.height * ratio))))

    image_format = str(payload.get("format", "jpeg")).strip().lower()
    quality = int(payload.get("quality", 75))
    content_type = "image/png" if image_format == "png" else "image/jpeg"
    extension = "png" if image_format == "png" else "jpg"
    buffer = BytesIO()
    if extension != "png" and image.mode != "RGB":
        image = image.convert("RGB")
    save_kwargs = {"format": "PNG"} if extension == "png" else {"format": "JPEG", "quality": quality, "optimize": True}
    image.save(buffer, **save_kwargs)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "artifact_base64": encoded,
        "artifact_ext": extension,
        "artifact_content_type": content_type,
        "screen_size": {"width": int(screen_width), "height": int(screen_height)},
        "image_size": {"width": int(image.width), "height": int(image.height)},
        "captured_at": _utcnow_iso(),
    }


def _mouse_move(payload: dict[str, Any]) -> dict[str, Any]:
    pyautogui = _pyautogui()
    pyautogui.moveTo(int(payload["x"]), int(payload["y"]), duration=float(payload.get("duration", 0)))
    return {"ok": True, "x": int(payload["x"]), "y": int(payload["y"])}


def _mouse_click(payload: dict[str, Any]) -> dict[str, Any]:
    pyautogui = _pyautogui()
    x = int(payload["x"])
    y = int(payload["y"])
    button = str(payload.get("button", "left"))
    clicks = int(payload.get("clicks", 1))
    pyautogui.click(x=x, y=y, button=button, clicks=clicks, interval=float(payload.get("interval", 0.08)))
    return {"ok": True, "x": x, "y": y, "button": button, "clicks": clicks}


def _mouse_drag(payload: dict[str, Any]) -> dict[str, Any]:
    pyautogui = _pyautogui()
    from_x = int(payload["from_x"])
    from_y = int(payload["from_y"])
    to_x = int(payload["to_x"])
    to_y = int(payload["to_y"])
    button = str(payload.get("button", "left"))
    duration = float(payload.get("duration", 0.3))
    pyautogui.moveTo(from_x, from_y, duration=0)
    pyautogui.dragTo(to_x, to_y, duration=duration, button=button)
    return {"ok": True, "from": {"x": from_x, "y": from_y}, "to": {"x": to_x, "y": to_y}, "button": button}


def _keyboard_type(payload: dict[str, Any]) -> dict[str, Any]:
    pyautogui = _pyautogui()
    text = str(payload.get("text", ""))
    pyautogui.write(text, interval=float(payload.get("interval", 0.01)))
    return {"ok": True, "typed_chars": len(text)}


def _keyboard_hotkey(payload: dict[str, Any]) -> dict[str, Any]:
    pyautogui = _pyautogui()
    keys = [str(item).strip() for item in payload.get("keys", []) if str(item).strip()]
    if not keys:
        raise ValueError("No hotkey keys were provided.")
    pyautogui.hotkey(*keys)
    return {"ok": True, "keys": keys}


def _keyboard_press(payload: dict[str, Any]) -> dict[str, Any]:
    pyautogui = _pyautogui()
    key = str(payload.get("key", "")).strip()
    if not key:
        raise ValueError("No key was provided.")
    pyautogui.press(key)
    return {"ok": True, "key": key}


def _file_list(payload: dict[str, Any]) -> dict[str, Any]:
    target = Path(str(payload.get("path", "."))).expanduser()
    if not target.exists():
        raise FileNotFoundError(f"{target} does not exist.")
    if not target.is_dir():
        raise NotADirectoryError(f"{target} is not a directory.")

    entries = []
    for item in sorted(target.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower())):
        try:
            stat = item.stat()
            size = stat.st_size
            modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        except OSError:
            size = None
            modified_at = None
        entries.append(
            {
                "name": item.name,
                "path": str(item),
                "is_dir": item.is_dir(),
                "size_bytes": size,
                "modified_at": modified_at,
            }
        )
    return {"path": str(target), "entries": entries}


def _file_read(payload: dict[str, Any]) -> dict[str, Any]:
    target = Path(str(payload.get("path", ""))).expanduser()
    max_bytes = int(payload.get("max_bytes", 50000))
    if not target.exists():
        raise FileNotFoundError(f"{target} does not exist.")
    if target.is_dir():
        raise IsADirectoryError(f"{target} is a directory.")

    raw = target.read_bytes()
    truncated = False
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
        truncated = True

    try:
        content = raw.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        content = raw.decode("utf-8", errors="replace")
        encoding = "utf-8-replace"

    return {
        "path": str(target),
        "content": content,
        "encoding": encoding,
        "truncated": truncated,
        "returned_bytes": len(raw),
    }


def _file_write(payload: dict[str, Any]) -> dict[str, Any]:
    target = Path(str(payload.get("path", ""))).expanduser()
    content = str(payload.get("content", ""))
    append = bool(payload.get("append", False))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a" if append else "w", encoding="utf-8") as handle:
        handle.write(content)
    return {"path": str(target), "bytes_written": len(content.encode("utf-8")), "append": append}


def _process_list(_: dict[str, Any]) -> dict[str, Any]:
    processes = []
    for process in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info"]):
        info = process.info
        memory_info = info.get("memory_info")
        processes.append(
            {
                "pid": info.get("pid"),
                "name": info.get("name"),
                "username": info.get("username"),
                "cpu_percent": info.get("cpu_percent"),
                "rss_bytes": getattr(memory_info, "rss", None),
            }
        )
    processes.sort(key=lambda item: ((item.get("name") or "").lower(), item.get("pid") or 0))
    return {"processes": processes[:400]}


def _process_kill(payload: dict[str, Any]) -> dict[str, Any]:
    pid = int(payload["pid"])
    process = psutil.Process(pid)
    process.terminate()
    try:
        process.wait(timeout=float(payload.get("timeout", 5)))
        terminated = True
    except psutil.TimeoutExpired:
        process.kill()
        terminated = False
    return {"pid": pid, "terminated_gracefully": terminated}


def _app_launch(payload: dict[str, Any]) -> dict[str, Any]:
    command = str(payload.get("command", "")).strip()
    args = [str(item) for item in payload.get("args", [])]
    if not command:
        raise ValueError("No application command was provided.")
    process = subprocess.Popen([command, *args])
    return {"pid": process.pid, "command": command, "args": args}


def _codex_exec(payload: dict[str, Any]) -> dict[str, Any]:
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        raise ValueError("No Codex prompt was provided.")

    codex_cli = _find_codex_cli()
    if codex_cli is None:
        raise RuntimeError("Codex CLI was not found on this device.")

    workspace_path_raw = str(payload.get("workspace_path", "")).strip()
    workspace_path: Path | None = None
    if workspace_path_raw:
        workspace_path = Path(workspace_path_raw).expanduser()
        if not workspace_path.exists():
            raise FileNotFoundError(f"{workspace_path} does not exist.")

    if _bool_value(payload.get("open_in_vscode"), default=True):
        executable = _find_vscode_cli()
        if executable is not None:
            launch_args = [executable]
            if workspace_path is not None:
                launch_args.append(str(workspace_path))
            subprocess.Popen(launch_args)

    timeout_seconds = int(payload.get("timeout_seconds", 900))
    model = str(payload.get("model", "")).strip()
    use_ephemeral = _bool_value(payload.get("ephemeral"), default=True)
    skip_git_repo_check = _bool_value(payload.get("skip_git_repo_check"), default=True)
    dangerously_bypass = _bool_value(payload.get("dangerously_bypass_approvals"), default=False)

    temp_dir = Path(tempfile.mkdtemp(prefix="ai_ops_codex_"))
    last_message_path = temp_dir / "last_message.txt"

    args = [codex_cli, "exec", "--full-auto", "-o", str(last_message_path)]
    if skip_git_repo_check:
        args.append("--skip-git-repo-check")
    if use_ephemeral:
        args.append("--ephemeral")
    if dangerously_bypass:
        args.append("--dangerously-bypass-approvals-and-sandbox")
    if model:
        args.extend(["-m", model])
    if workspace_path is not None:
        args.extend(["-C", str(workspace_path)])
    args.append(prompt)

    completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout_seconds)
    last_message = last_message_path.read_text(encoding="utf-8", errors="replace") if last_message_path.exists() else ""
    stdout_text = completed.stdout.strip()
    stderr_text = completed.stderr.strip()
    output_text = last_message or stdout_text or stderr_text

    if completed.returncode != 0:
        error_text = stderr_text or stdout_text or f"Codex exited with code {completed.returncode}"
        raise RuntimeError(error_text)

    result = {
        "ok": True,
        "codex_cli": codex_cli,
        "returncode": completed.returncode,
        "workspace_path": str(workspace_path) if workspace_path is not None else None,
        "prompt": prompt,
        "model": model or None,
        "last_message_excerpt": _truncate_text(output_text, 3200) if output_text else "",
        "stdout_excerpt": _truncate_text(stdout_text, 1200) if stdout_text else "",
    }
    if output_text:
        result["artifact_base64"] = base64.b64encode(output_text.encode("utf-8")).decode("ascii")
        result["artifact_ext"] = "txt"
        result["artifact_content_type"] = "text/plain"
    return result


def _app_action(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "")).strip()
    if action == "browser_open_url":
        url = str(payload.get("url", "")).strip()
        if not url:
            raise ValueError("No URL was provided.")
        webbrowser.open(url, new=2)
        return {"ok": True, "action": action, "url": url}

    if action == "file_manager_reveal":
        target = Path(str(payload.get("path", ""))).expanduser()
        if not target.exists():
            raise FileNotFoundError(f"{target} does not exist.")
        system = platform.system()
        if system == "Windows":
            subprocess.Popen(["explorer", "/select,", str(target)])
        elif system == "Darwin":
            subprocess.Popen(["open", "-R", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target.parent if target.is_file() else target)])
        return {"ok": True, "action": action, "path": str(target)}

    if action == "vscode_open_path":
        target_raw = str(payload.get("path", "")).strip()
        executable = _find_vscode_cli()
        if executable is None:
            raise RuntimeError("VS Code CLI was not found (`code` or `code-insiders`).")
        if target_raw:
            target = Path(target_raw).expanduser()
            subprocess.Popen([executable, str(target)])
            return {"ok": True, "action": action, "path": str(target), "executable": executable}
        subprocess.Popen([executable])
        return {"ok": True, "action": action, "path": None, "executable": executable}

    if action in {"codex_exec", "vscode_codex_prompt"}:
        result = _codex_exec(payload)
        result["action"] = action
        return result

    raise ValueError(f"Unsupported app action `{action}`.")


def _window_list(_: dict[str, Any]) -> dict[str, Any]:
    gw = _load_windows_module()
    if gw is None:
        raise RuntimeError("Window enumeration is not available on this platform or install.")
    windows = []
    for window in gw.getAllWindows():
        title = getattr(window, "title", "")
        if not title:
            continue
        windows.append(
            {
                "title": title,
                "left": getattr(window, "left", None),
                "top": getattr(window, "top", None),
                "width": getattr(window, "width", None),
                "height": getattr(window, "height", None),
                "is_minimized": getattr(window, "isMinimized", False),
            }
        )
    return {"windows": windows}


def _window_focus(payload: dict[str, Any]) -> dict[str, Any]:
    gw = _load_windows_module()
    if gw is None:
        raise RuntimeError("Window focus control is not available on this platform or install.")
    title_contains = str(payload.get("title_contains", "")).strip().lower()
    if not title_contains:
        raise ValueError("No window title filter was provided.")

    for window in gw.getAllWindows():
        title = getattr(window, "title", "")
        if title_contains in title.lower():
            try:
                if getattr(window, "isMinimized", False):
                    window.restore()
                window.activate()
            except Exception:
                pass
            return {"ok": True, "title": title}
    raise RuntimeError(f"No window matched `{title_contains}`.")


COMMAND_HANDLERS = {
    "screenshot": _screenshot,
    "mouse_move": _mouse_move,
    "mouse_click": _mouse_click,
    "mouse_drag": _mouse_drag,
    "keyboard_type": _keyboard_type,
    "keyboard_hotkey": _keyboard_hotkey,
    "keyboard_press": _keyboard_press,
    "file_list": _file_list,
    "file_read": _file_read,
    "file_write": _file_write,
    "process_list": _process_list,
    "process_kill": _process_kill,
    "app_launch": _app_launch,
    "app_action": _app_action,
    "window_list": _window_list,
    "window_focus": _window_focus,
}


def execute_control_command(command: dict[str, Any], config: AgentConfig) -> tuple[str, dict[str, Any], str | None]:
    command_type = str(command.get("command_type", "")).strip()
    payload = command.get("payload_json", {}) or {}
    handler = COMMAND_HANDLERS.get(command_type)
    if handler is None:
        return "failed", {}, f"Unsupported control command `{command_type}`."

    try:
        result = handler(payload)
        if isinstance(result, dict):
            result.setdefault("agent_name", config.agent_name)
            result.setdefault("executed_at", _utcnow_iso())
        return "completed", result, None
    except Exception as exc:
        return "failed", {}, str(exc)
