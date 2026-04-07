import os
import platform
from pathlib import Path

from ai_ops_agent.constants import CONFIG_FILENAME, LOG_FILENAME, APP_LABEL, LINUX_SERVICE_FILENAME, MAC_LAUNCH_AGENT_FILENAME


def app_data_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / APP_LABEL
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_LABEL
    base = Path(os.getenv("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / APP_LABEL


def logs_dir() -> Path:
    return app_data_dir() / "logs"


def config_path() -> Path:
    return app_data_dir() / CONFIG_FILENAME


def log_path() -> Path:
    return logs_dir() / LOG_FILENAME


def mac_launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / MAC_LAUNCH_AGENT_FILENAME


def linux_systemd_service_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / LINUX_SERVICE_FILENAME


def ensure_runtime_dirs() -> None:
    app_data_dir().mkdir(parents=True, exist_ok=True)
    logs_dir().mkdir(parents=True, exist_ok=True)
