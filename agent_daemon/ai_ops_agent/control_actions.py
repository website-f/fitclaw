from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import heapq
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import time as time_module
from typing import Any
from urllib.parse import urlencode
import webbrowser
from zoneinfo import ZoneInfo

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


def _load_uiautomation_module():
    if platform.system() != "Windows":
        return None
    try:
        import uiautomation as auto
    except Exception:
        return None
    return auto


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
    capabilities.update({"shell", "file_system", "processes", "storage", "calendar"})
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


def _format_bytes(value: int | float | None) -> str:
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


def _default_storage_scan_path() -> Path:
    if platform.system() == "Windows":
        home_drive = Path.home().drive
        if home_drive:
            return Path(f"{home_drive}\\")
        system_drive = os.environ.get("SystemDrive", "C:")
        return Path(f"{system_drive}\\")
    return Path.home()


def _is_root_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    anchor = resolved.anchor or str(resolved)
    return str(resolved).rstrip("\\/") == str(Path(anchor)).rstrip("\\/")


def _program_root_candidates(target: Path) -> list[Path]:
    candidates: list[Path] = []
    if platform.system() == "Windows":
        drive = target.drive or Path.home().drive or os.environ.get("SystemDrive", "C:")
        for raw in (
            f"{drive}\\Program Files",
            f"{drive}\\Program Files (x86)",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
        ):
            if raw:
                path = Path(raw)
                if path.exists() and path.is_dir():
                    candidates.append(path)
    return candidates


def _directory_size(path: Path) -> tuple[int, int]:
    total_size = 0
    scanned_files = 0
    for root, _, files in os.walk(path, topdown=True):
        for filename in files:
            file_path = Path(root) / filename
            try:
                total_size += file_path.stat().st_size
                scanned_files += 1
            except (FileNotFoundError, PermissionError, OSError):
                continue
    return total_size, scanned_files


def _top_app_like_folders(target: Path, top_n: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for root in _program_root_candidates(target):
        try:
            children = [item for item in root.iterdir() if item.is_dir()]
        except (FileNotFoundError, PermissionError, OSError):
            continue

        for child in children:
            size_bytes, scanned_files = _directory_size(child)
            results.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "root": str(root),
                    "size_bytes": size_bytes,
                    "size_human": _format_bytes(size_bytes),
                    "scanned_files": scanned_files,
                }
            )
    results.sort(key=lambda item: item["size_bytes"], reverse=True)
    return results[:top_n]


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


def _storage_summary(payload: dict[str, Any]) -> dict[str, Any]:
    requested_path = str(payload.get("path", "")).strip()
    target = Path(requested_path).expanduser() if requested_path else _default_storage_scan_path()
    if not target.exists():
        raise FileNotFoundError(f"{target} does not exist.")

    target_usage = psutil.disk_usage(str(target))
    partitions = []
    seen_mounts: set[str] = set()
    for partition in psutil.disk_partitions(all=False):
        mountpoint = str(partition.mountpoint)
        if not mountpoint or mountpoint in seen_mounts:
            continue
        seen_mounts.add(mountpoint)
        try:
            usage = psutil.disk_usage(mountpoint)
        except Exception:
            continue
        partitions.append(
            {
                "device": partition.device,
                "mountpoint": mountpoint,
                "fstype": partition.fstype,
                "opts": partition.opts,
                "total_bytes": int(usage.total),
                "used_bytes": int(usage.used),
                "free_bytes": int(usage.free),
                "percent": float(usage.percent),
            }
        )

    partitions.sort(key=lambda item: item["total_bytes"], reverse=True)
    return {
        "path": str(target),
        "target_usage": {
            "total_bytes": int(target_usage.total),
            "used_bytes": int(target_usage.used),
            "free_bytes": int(target_usage.free),
            "percent": float(target_usage.percent),
        },
        "partitions": partitions,
        "captured_at": _utcnow_iso(),
    }


def _disk_usage_scan(payload: dict[str, Any]) -> dict[str, Any]:
    requested_path = str(payload.get("path", "")).strip()
    target = Path(requested_path).expanduser() if requested_path else _default_storage_scan_path()
    if not target.exists():
        raise FileNotFoundError(f"{target} does not exist.")
    if not target.is_dir():
        raise NotADirectoryError(f"{target} is not a directory.")

    top_n = min(max(int(payload.get("top_n", 10)), 1), 50)
    include_hidden = _bool_value(payload.get("include_hidden"), default=False)
    shallow_root_scan = _bool_value(payload.get("shallow_root_scan"), default=_is_root_path(target))
    file_heap: list[tuple[int, str]] = []
    folder_heap: list[tuple[int, str]] = []
    scanned_files = 0
    scanned_dirs = 0
    skipped_entries = 0

    def push_top(heap: list[tuple[int, str]], size: int, path_value: str) -> None:
        item = (int(size), path_value)
        if len(heap) < top_n:
            heapq.heappush(heap, item)
            return
        if size > heap[0][0]:
            heapq.heapreplace(heap, item)

    def walk_directory(path: Path, is_root: bool = False) -> int:
        nonlocal scanned_files, scanned_dirs, skipped_entries
        total_size = 0
        try:
            with os.scandir(path) as iterator:
                for entry in iterator:
                    name = entry.name
                    if not include_hidden and name.startswith("."):
                        continue
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            scanned_dirs += 1
                            child_size = walk_directory(Path(entry.path), is_root=False)
                            total_size += child_size
                            push_top(folder_heap, child_size, entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            stat = entry.stat(follow_symlinks=False)
                            size = int(stat.st_size)
                            scanned_files += 1
                            total_size += size
                            push_top(file_heap, size, entry.path)
                    except (FileNotFoundError, PermissionError, OSError):
                        skipped_entries += 1
        except (FileNotFoundError, PermissionError, OSError):
            skipped_entries += 1
            return 0

        if not is_root:
            return total_size
        return total_size

    if shallow_root_scan:
        total_scanned_size = 0
        try:
            entries = list(target.iterdir())
        except (FileNotFoundError, PermissionError, OSError):
            entries = []
            skipped_entries += 1

        for entry in entries:
            if not include_hidden and entry.name.startswith("."):
                continue
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    scanned_dirs += 1
                    child_size, child_files = _directory_size(entry)
                    scanned_files += child_files
                    total_scanned_size += child_size
                    push_top(folder_heap, child_size, str(entry))
                elif entry.is_file():
                    stat = entry.stat()
                    size = int(stat.st_size)
                    scanned_files += 1
                    total_scanned_size += size
                    push_top(file_heap, size, str(entry))
            except (FileNotFoundError, PermissionError, OSError):
                skipped_entries += 1
    else:
        total_scanned_size = walk_directory(target, is_root=True)

    top_files = [
        {"path": path_value, "size_bytes": size, "size_human": _format_bytes(size)}
        for size, path_value in sorted(file_heap, reverse=True)
    ]
    top_folders = [
        {"path": path_value, "size_bytes": size, "size_human": _format_bytes(size)}
        for size, path_value in sorted(folder_heap, reverse=True)
    ]
    return {
        "path": str(target),
        "top_n": top_n,
        "scanned_files": scanned_files,
        "scanned_dirs": scanned_dirs,
        "skipped_entries": skipped_entries,
        "estimated_total_bytes": total_scanned_size,
        "estimated_total_human": _format_bytes(total_scanned_size),
        "scan_mode": "shallow_root" if shallow_root_scan else "deep",
        "top_files": top_files,
        "top_folders": top_folders,
        "scanned_at": _utcnow_iso(),
    }


def _storage_breakdown(payload: dict[str, Any]) -> dict[str, Any]:
    requested_path = str(payload.get("path", "")).strip()
    target = Path(requested_path).expanduser() if requested_path else _default_storage_scan_path()
    if not target.exists():
        raise FileNotFoundError(f"{target} does not exist.")
    if not target.is_dir():
        raise NotADirectoryError(f"{target} is not a directory.")

    top_n = min(max(int(payload.get("top_n", 10)), 1), 50)
    summary = _storage_summary({"path": str(target)})
    scan = _disk_usage_scan({"path": str(target), "top_n": top_n, "include_hidden": payload.get("include_hidden", False)})
    top_apps = _top_app_like_folders(target, top_n)

    return {
        "path": str(target),
        "top_n": top_n,
        "target_usage": summary.get("target_usage", {}),
        "partitions": summary.get("partitions", []),
        "top_files": scan.get("top_files", []),
        "top_folders": scan.get("top_folders", []),
        "top_apps": top_apps,
        "scanned_files": scan.get("scanned_files", 0),
        "scanned_dirs": scan.get("scanned_dirs", 0),
        "skipped_entries": scan.get("skipped_entries", 0),
        "estimated_total_bytes": scan.get("estimated_total_bytes", 0),
        "estimated_total_human": scan.get("estimated_total_human", "0 B"),
        "captured_at": _utcnow_iso(),
    }


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


def _file_delete(payload: dict[str, Any]) -> dict[str, Any]:
    target = Path(str(payload.get("path", ""))).expanduser()
    use_trash = _bool_value(payload.get("use_trash"), default=True)
    if not target.exists():
        raise FileNotFoundError(f"{target} does not exist.")

    deleted_type = "directory" if target.is_dir() else "file"
    method = "permanent_delete"

    if use_trash and platform.system() == "Windows":
        quoted_path = str(target).replace("'", "''")
        powershell_script = f"""
Add-Type -AssemblyName Microsoft.VisualBasic
$Target = '{quoted_path}'
if (Test-Path -LiteralPath $Target -PathType Container) {{
  [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory(
    $Target,
    [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
    [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin
  )
}} else {{
  [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
    $Target,
    [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
    [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin
  )
}}
""".strip()
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", powershell_script],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        method = "recycle_bin"
    else:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    return {
        "ok": True,
        "path": str(target),
        "deleted_type": deleted_type,
        "method": method,
        "deleted_at": _utcnow_iso(),
    }


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


def _running_browser_processes() -> list[str]:
    browser_names = {
        "chrome.exe": "Google Chrome",
        "msedge.exe": "Microsoft Edge",
        "brave.exe": "Brave",
        "firefox.exe": "Firefox",
        "arc.exe": "Arc",
        "opera.exe": "Opera",
        "vivaldi.exe": "Vivaldi",
        "safari": "Safari",
        "google chrome": "Google Chrome",
        "microsoft edge": "Microsoft Edge",
        "firefox": "Firefox",
    }
    results: list[str] = []
    seen: set[str] = set()
    for process in psutil.process_iter(["name"]):
        name = str(process.info.get("name") or "").strip().lower()
        if not name:
            continue
        label = browser_names.get(name)
        if not label or label in seen:
            continue
        seen.add(label)
        results.append(label)
    return sorted(results)


def _find_outlook_executable() -> str | None:
    candidate = shutil.which("outlook")
    if candidate:
        return candidate

    if platform.system() != "Windows":
        return None

    drive = Path.home().drive or os.environ.get("SystemDrive", "C:")
    search_roots = [
        Path(f"{drive}\\Program Files\\Microsoft Office"),
        Path(f"{drive}\\Program Files (x86)\\Microsoft Office"),
        Path(f"{drive}\\Program Files\\Microsoft Office\\root"),
        Path(f"{drive}\\Program Files (x86)\\Microsoft Office\\root"),
    ]
    for root in search_roots:
        if not root.exists():
            continue
        for match in root.rglob("OUTLOOK.EXE"):
            return str(match)
    return None


def _calendar_windows_snapshot() -> list[dict[str, Any]]:
    gw = _load_windows_module()
    if gw is None:
        return []

    results: list[dict[str, Any]] = []
    for window in gw.getAllWindows():
        title = str(getattr(window, "title", "") or "").strip()
        if not title:
            continue
        lowered = title.lower()
        if not any(token in lowered for token in ("calendar", "outlook", "gmail")):
            continue
        results.append(
            {
                "title": title,
                "width": getattr(window, "width", None),
                "height": getattr(window, "height", None),
                "is_minimized": getattr(window, "isMinimized", False),
            }
        )
    return results[:20]


def _is_outlook_onboarding_title(title: str) -> bool:
    lowered = str(title or "").strip().lower()
    return any(
        token in lowered
        for token in (
            "welcome to outlook",
            "add your email account",
            "outlook 2016",
            "outlook setup",
            "account setup",
        )
    )


def _close_windows_matching(tokens: list[str]) -> list[str]:
    gw = _load_windows_module()
    if gw is None:
        return []

    normalized_tokens = [item.strip().lower() for item in tokens if item and item.strip()]
    closed: list[str] = []
    for window in gw.getAllWindows():
        title = str(getattr(window, "title", "") or "").strip()
        lowered = title.lower()
        if not title or not any(token in lowered for token in normalized_tokens):
            continue
        try:
            window.close()
            closed.append(title)
        except Exception:
            continue
    return closed


def _looks_like_google_calendar_title(title: str, title_hint: str | None = None) -> bool:
    lowered = str(title or "").strip().lower()
    if not lowered:
        return False
    if "google calendar" in lowered or "calendar.google.com" in lowered:
        return True
    if "calendar" in lowered and ("event details" in lowered or "find a time" in lowered or "add guests" in lowered):
        return True

    normalized_hint = str(title_hint or "").strip().lower()
    browser_markers = ("brave", "chrome", "edge", "firefox", "opera", "vivaldi", "arc")
    if "calendar" in lowered and any(marker in lowered for marker in browser_markers):
        if normalized_hint and normalized_hint in lowered:
            return True
    return False


def _calendar_probe(_: dict[str, Any]) -> dict[str, Any]:
    windows = _calendar_windows_snapshot()
    titles = [str(item.get("title", "")).lower() for item in windows]
    running_browsers = _running_browser_processes()
    has_google_calendar_window = any(_looks_like_google_calendar_title(title) for title in titles)
    has_outlook_window = any("outlook" in title for title in titles)
    outlook_onboarding_detected = any(_is_outlook_onboarding_title(str(item.get("title", ""))) for item in windows)
    outlook_executable = _find_outlook_executable()
    outlook_running = any(
        str(process.info.get("name") or "").strip().lower() == "outlook.exe"
        for process in psutil.process_iter(["name"])
    )
    outlook_available = bool((has_outlook_window or outlook_running) and not outlook_onboarding_detected)

    recommended_provider = "google"
    reason = "I can open a prefilled Google Calendar event in the default browser on this device."
    if has_google_calendar_window:
        recommended_provider = "google"
        reason = "Google Calendar already appears to be open on this device."
    elif outlook_available:
        recommended_provider = "outlook"
        reason = "Outlook looks available on this device, so the event can usually be saved directly."
    elif outlook_onboarding_detected:
        recommended_provider = "google"
        reason = "Outlook is installed but appears to be in first-run setup, so Google Calendar is the safer path."
    elif running_browsers:
        recommended_provider = "google"
        reason = "A browser is already running, so opening a prefilled Google Calendar event is the best next option."

    return {
        "calendar_windows": windows,
        "has_google_calendar_window": has_google_calendar_window,
        "has_outlook_window": has_outlook_window,
        "outlook_onboarding_detected": outlook_onboarding_detected,
        "outlook_available": outlook_available,
        "outlook_executable": outlook_executable,
        "running_browsers": running_browsers,
        "recommended_provider": recommended_provider,
        "reason": reason,
        "probed_at": _utcnow_iso(),
    }


def _parse_event_datetime(raw: str | None) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is not None:
        return parsed.astimezone()
    return parsed.replace(tzinfo=timezone.utc).astimezone()


def _calendar_timezone(payload: dict[str, Any]) -> ZoneInfo:
    timezone_name = str(payload.get("timezone") or "").strip()
    if timezone_name:
        try:
            return ZoneInfo(timezone_name)
        except Exception:
            pass
    return datetime.now().astimezone().tzinfo or ZoneInfo("UTC")


def _calendar_is_all_day(payload: dict[str, Any], starts_at: datetime, ends_at: datetime) -> bool:
    if _bool_value(payload.get("all_day"), default=False):
        return True
    tz = _calendar_timezone(payload)
    start_local = starts_at.astimezone(tz)
    end_local = ends_at.astimezone(tz)
    return (
        start_local.time() == datetime.min.time()
        and end_local.time() == datetime.min.time()
        and (end_local - start_local) >= timedelta(days=1)
    )


def _ics_escape(value: str | None) -> str:
    return str(value or "").replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _build_google_calendar_url(payload: dict[str, Any]) -> str:
    starts_at = _parse_event_datetime(payload.get("starts_at"))
    ends_at = _parse_event_datetime(payload.get("ends_at"))
    if starts_at is None:
        raise ValueError("Calendar start time is required.")
    if ends_at is None:
        ends_at = starts_at
    tz = _calendar_timezone(payload)
    all_day = _calendar_is_all_day(payload, starts_at, ends_at)

    def format_utc(value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    params = {
        "action": "TEMPLATE",
        "text": str(payload.get("title", "")).strip(),
        "details": str(payload.get("description") or "").strip(),
        "location": str(payload.get("location") or "").strip(),
    }
    if all_day:
        start_local = starts_at.astimezone(tz)
        end_local = ends_at.astimezone(tz)
        if end_local <= start_local:
            end_local = start_local + timedelta(days=1)
        params["dates"] = f"{start_local.strftime('%Y%m%d')}/{end_local.strftime('%Y%m%d')}"
    else:
        params["dates"] = f"{format_utc(starts_at)}/{format_utc(ends_at)}"
    timezone_name = str(payload.get("timezone") or "").strip()
    if timezone_name:
        params["ctz"] = timezone_name
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def _open_with_default_app(target: Path) -> None:
    system = platform.system()
    if system == "Windows":
        os.startfile(str(target))  # type: ignore[attr-defined]
        return
    if system == "Darwin":
        subprocess.Popen(["open", str(target)])
        return
    subprocess.Popen(["xdg-open", str(target)])


def _write_calendar_ics(payload: dict[str, Any]) -> Path:
    starts_at = _parse_event_datetime(payload.get("starts_at"))
    if starts_at is None:
        raise ValueError("Calendar start time is required.")
    ends_at = _parse_event_datetime(payload.get("ends_at")) or starts_at
    event_id = str(payload.get("event_id") or f"aiops-{int(datetime.now(timezone.utc).timestamp())}")
    temp_dir = Path(tempfile.mkdtemp(prefix="ai_ops_calendar_"))
    output_path = temp_dir / f"{event_id}.ics"
    description = str(payload.get("description") or "Created by Personal AI Ops Platform").strip()

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//FitClaw//Personal AI Ops Agent//EN",
        "BEGIN:VEVENT",
        f"UID:{event_id}@fitclaw.aiops",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{starts_at.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTEND:{ends_at.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"SUMMARY:{_ics_escape(payload.get('title'))}",
        f"DESCRIPTION:{_ics_escape(description)}",
        "STATUS:CONFIRMED",
    ]
    location = str(payload.get("location") or "").strip()
    if location:
        lines.append(f"LOCATION:{_ics_escape(location)}")
    meeting_url = str(payload.get("meeting_url") or "").strip()
    if meeting_url:
        lines.append(f"URL:{meeting_url}")
    lines.extend(["END:VEVENT", "END:VCALENDAR", ""])
    output_path.write_text("\r\n".join(lines), encoding="utf-8")
    return output_path


def _create_outlook_event(payload: dict[str, Any]) -> dict[str, Any]:
    if platform.system() != "Windows":
        raise RuntimeError("Direct Outlook calendar creation is only available on Windows agents.")

    existing_windows = _calendar_windows_snapshot()
    if any(_is_outlook_onboarding_title(str(item.get("title", ""))) for item in existing_windows):
        _close_windows_matching(["welcome to outlook", "outlook setup", "add your email account"])
        raise RuntimeError(
            "Outlook is installed but not configured on this device yet. Use Google Calendar instead, or finish Outlook setup first."
        )

    starts_at = _parse_event_datetime(payload.get("starts_at"))
    if starts_at is None:
        raise ValueError("Calendar start time is required.")
    ends_at = _parse_event_datetime(payload.get("ends_at")) or starts_at
    reminder_minutes_before = int(payload.get("reminder_minutes_before") or 30)

    script_payload = {
        "title": str(payload.get("title") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
        "location": str(payload.get("location") or "").strip(),
        "meeting_url": str(payload.get("meeting_url") or "").strip(),
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "reminder_minutes_before": reminder_minutes_before,
    }
    payload_b64 = base64.b64encode(json.dumps(script_payload).encode("utf-8")).decode("ascii")
    powershell_script = f"""
$ErrorActionPreference = 'Stop'
$PayloadJson = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{payload_b64}'))
$Payload = $PayloadJson | ConvertFrom-Json
$Outlook = New-Object -ComObject Outlook.Application
$Appointment = $Outlook.CreateItem(1)
$Appointment.Subject = [string]$Payload.title
$Appointment.Start = [DateTime]::Parse([string]$Payload.starts_at).ToLocalTime().ToString('yyyy-MM-dd HH:mm:ss')
$Appointment.End = [DateTime]::Parse([string]$Payload.ends_at).ToLocalTime().ToString('yyyy-MM-dd HH:mm:ss')
$Appointment.Location = [string]$Payload.location
$Body = [string]$Payload.description
if ([string]::IsNullOrWhiteSpace($Body)) {{
  $Body = 'Created by Personal AI Ops Platform'
}}
if (-not [string]::IsNullOrWhiteSpace([string]$Payload.meeting_url)) {{
  $Body = ($Body.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + 'Meeting URL: ' + [string]$Payload.meeting_url)
}}
$Appointment.Body = $Body
$Appointment.ReminderSet = $true
$Appointment.ReminderMinutesBeforeStart = [int]$Payload.reminder_minutes_before
$Appointment.BusyStatus = 2
$Appointment.Save()
Write-Output 'saved'
""".strip()

    completed = subprocess.run(
        ["powershell", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", powershell_script],
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=True,
    )

    refreshed_windows = _calendar_windows_snapshot()
    if any(_is_outlook_onboarding_title(str(item.get("title", ""))) for item in refreshed_windows):
        _close_windows_matching(["welcome to outlook", "outlook setup", "add your email account"])
        raise RuntimeError(
            "Outlook opened its first-run setup instead of saving the event. Google Calendar is the better option on this device."
        )

    return {
        "ok": True,
        "provider_used": "outlook",
        "saved": True,
        "stdout": completed.stdout.strip(),
    }


def _find_google_calendar_window(title_hint: str, attempts: int = 20, delay_seconds: float = 0.6):
    gw = _load_windows_module()
    if gw is None:
        return None, None

    for _ in range(max(attempts, 1)):
        best_match = None
        best_score = -1
        for window in gw.getAllWindows():
            title = str(getattr(window, "title", "") or "").strip()
            if not title:
                continue
            if not _looks_like_google_calendar_title(title, title_hint):
                continue
            lowered = title.lower()
            score = 0
            if "google calendar" in lowered or "calendar.google.com" in lowered:
                score += 4
            if "event details" in lowered:
                score += 3
            if "calendar" in lowered:
                score += 2
            if str(title_hint or "").strip().lower() and str(title_hint).strip().lower() in lowered:
                score += 2
            if score > best_score:
                best_match = (window, title)
                best_score = score
        if best_match is not None:
            return best_match
        time_module.sleep(delay_seconds)
    return None, None


def _google_calendar_window_still_editing(title: str | None) -> bool:
    lowered = str(title or "").strip().lower()
    if not lowered:
        return True
    return "event details" in lowered or "find a time" in lowered


def _find_google_calendar_save_button(title_hint: str, attempts: int = 30, delay_seconds: float = 0.75):
    auto = _load_uiautomation_module()
    if auto is None:
        return None, None

    normalized_hint = str(title_hint or "").strip().lower()
    for _ in range(max(attempts, 1)):
        best_match = None
        best_score = -1
        root = auto.GetRootControl()
        for window in root.GetChildren():
            title = str(getattr(window, "Name", "") or "").strip()
            if not title or not _looks_like_google_calendar_title(title, title_hint):
                continue

            try:
                button = window.ButtonControl(searchDepth=30, Name="Save")
                exists = button.Exists(0, 0)
            except Exception:
                continue
            if not exists:
                continue

            score = 0
            lowered = title.lower()
            if "event details" in lowered:
                score += 4
            if "google calendar" in lowered or "calendar.google.com" in lowered:
                score += 3
            if "calendar" in lowered:
                score += 2
            if normalized_hint and normalized_hint in lowered:
                score += 1

            if score > best_score:
                best_match = (button, title)
                best_score = score

        if best_match is not None:
            return best_match
        time_module.sleep(delay_seconds)
    return None, None


def _attempt_google_calendar_auto_save_uia(payload: dict[str, Any]) -> dict[str, Any] | None:
    auto = _load_uiautomation_module()
    if auto is None:
        return None

    button, matched_title = _find_google_calendar_save_button(str(payload.get("title") or ""))
    if button is None:
        return {
            "attempted": False,
            "saved": False,
            "method": "uiautomation",
            "reason": "Could not find an accessible Google Calendar Save button in time.",
        }

    final_title = matched_title
    last_error = None
    for attempt in range(3):
        try:
            button.SetFocus()
        except Exception:
            pass
        time_module.sleep(0.25)
        action_method = "uia-click"
        try:
            invoke_pattern = button.GetInvokePattern()
            invoke_pattern.Invoke()
            action_method = "uia-invoke"
        except Exception as exc:
            last_error = str(exc)
            try:
                button.Click()
                action_method = "uia-click"
            except Exception as click_exc:
                last_error = f"{exc}; click fallback: {click_exc}"
        time_module.sleep(1.4 + (attempt * 0.4))

        try:
            foreground = auto.GetForegroundControl()
            final_title = str(getattr(foreground, "Name", "") or "").strip() or final_title
        except Exception:
            pass

        if not _google_calendar_window_still_editing(final_title):
            return {
                "attempted": True,
                "saved": True,
                "method": action_method,
                "window_title": matched_title,
                "final_window_title": final_title,
                "attempts": attempt + 1,
            }

    result = {
        "attempted": True,
        "saved": False,
        "method": "uiautomation",
        "window_title": matched_title,
        "final_window_title": final_title,
        "attempts": 3,
    }
    if last_error:
        result["reason"] = last_error
    return result


def _attempt_google_calendar_auto_save(payload: dict[str, Any]) -> dict[str, Any]:
    if platform.system() != "Windows":
        return {"attempted": False, "reason": "Automatic Google Calendar save is currently available on Windows desktop agents only."}

    uia_result = _attempt_google_calendar_auto_save_uia(payload)
    if uia_result is not None and uia_result.get("saved"):
        return uia_result
    if not _has_pyautogui():
        return uia_result or {"attempted": False, "reason": "Mouse and keyboard automation is unavailable on this agent build."}

    window, matched_title = _find_google_calendar_window(str(payload.get("title") or ""))
    if window is None:
        if uia_result is not None:
            return uia_result
        return {"attempted": False, "reason": "Could not find the Google Calendar browser window in time."}

    try:
        if getattr(window, "isMinimized", False):
            window.restore()
    except Exception:
        pass
    try:
        window.activate()
    except Exception:
        pass

    time_module.sleep(2.0)
    pyautogui = _pyautogui()
    left = int(getattr(window, "left", 0) or 0)
    top = int(getattr(window, "top", 0) or 0)
    width = int(getattr(window, "width", 0) or 0)
    height = int(getattr(window, "height", 0) or 0)
    if width <= 0 or height <= 0:
        return {"attempted": False, "reason": "The Google Calendar window geometry was not available for automation."}

    save_x = left + min(max(int(width * 0.45), 160), max(width - 160, 160))
    save_y = top + min(max(int(height * 0.08), 80), 130)

    final_title = matched_title
    for attempt in range(3):
        try:
            window.activate()
        except Exception:
            pass
        time_module.sleep(0.4)
        pyautogui.click(save_x, save_y)
        time_module.sleep(1.4 + (attempt * 0.4))
        final_title = str(getattr(window, "title", "") or "").strip() or final_title
        if not _google_calendar_window_still_editing(final_title):
            return {
                "attempted": True,
                "saved": True,
                "method": "click-save-button",
                "window_title": matched_title,
                "final_window_title": final_title,
                "click_point": {"x": save_x, "y": save_y},
                "attempts": attempt + 1,
            }

    return {
        "attempted": True,
        "saved": False,
        "method": "click-save-button",
        "window_title": matched_title,
        "final_window_title": final_title,
        "click_point": {"x": save_x, "y": save_y},
        "attempts": 3,
        "fallback_from": uia_result.get("method") if isinstance(uia_result, dict) else None,
        "reason": (uia_result or {}).get("reason") if isinstance(uia_result, dict) else None,
    }


def _calendar_create(payload: dict[str, Any]) -> dict[str, Any]:
    probe = _calendar_probe({})
    preferred_provider = str(payload.get("provider") or "").strip().lower()
    provider = preferred_provider or str(probe.get("recommended_provider") or "google")

    if provider == "outlook" and not probe.get("outlook_available"):
        if preferred_provider == "outlook":
            raise RuntimeError("Outlook is not ready on this device. Try Google Calendar instead.")
        provider = "google"

    if provider == "outlook":
        try:
            result = _create_outlook_event(payload)
            result["probe"] = probe
            return result
        except Exception as exc:
            if preferred_provider == "outlook":
                raise
            payload = dict(payload)
            payload["_outlook_error"] = str(exc)
            provider = "google"

    if provider == "google":
        url = _build_google_calendar_url(payload)
        webbrowser.open(url, new=2)
        auto_save = _attempt_google_calendar_auto_save(payload)
        return {
            "ok": True,
            "provider_used": "google",
            "opened": True,
            "saved": bool(auto_save.get("saved")),
            "requires_user_confirmation": not bool(auto_save.get("saved")),
            "auto_save_attempted": bool(auto_save.get("attempted")),
            "auto_save_result": auto_save,
            "opened_url": url,
            "probe": probe,
            "outlook_error": payload.get("_outlook_error"),
        }

    ics_path = _write_calendar_ics(payload)
    _open_with_default_app(ics_path)
    return {
        "ok": True,
        "provider_used": "ics",
        "opened": True,
        "saved": False,
        "requires_user_confirmation": True,
        "ics_path": str(ics_path),
        "probe": probe,
        "outlook_error": payload.get("_outlook_error"),
    }


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

    if action == "calendar_probe":
        result = _calendar_probe(payload)
        result["action"] = action
        return result

    if action == "calendar_create":
        result = _calendar_create(payload)
        result["action"] = action
        return result

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
    "storage_summary": _storage_summary,
    "disk_usage_scan": _disk_usage_scan,
    "storage_breakdown": _storage_breakdown,
    "file_list": _file_list,
    "file_read": _file_read,
    "file_write": _file_write,
    "file_delete": _file_delete,
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
