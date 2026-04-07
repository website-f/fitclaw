from __future__ import annotations

import os
from pathlib import Path
import plistlib
import platform
import shlex
import subprocess
import sys
from typing import Sequence

from ai_ops_agent.config import AgentConfig
from ai_ops_agent.constants import APP_BUNDLE_ID, APP_NAME, RUN_KEY_NAME
from ai_ops_agent.logging_utils import configure_logging
from ai_ops_agent.paths import app_data_dir, config_path, ensure_runtime_dirs, linux_systemd_service_path, mac_launch_agent_path
from ai_ops_agent.runtime import AgentRunner


def launcher_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "run-agent", "--background"]

    script_path = Path(__file__).resolve().parents[1] / "agent_daemon.py"
    return [sys.executable, str(script_path), "run-agent", "--background"]


def test_connection(config: AgentConfig) -> None:
    logger = configure_logging(background=False)
    runner = AgentRunner(config, logger=logger)
    runner.test_connectivity()


def save_config(config: AgentConfig) -> None:
    errors = config.validate()
    if errors:
        raise ValueError("\n".join(errors))
    ensure_runtime_dirs()
    config.save()


def install_agent(config: AgentConfig, start_now: bool = True) -> str:
    save_config(config)
    test_connection(config)

    if config.auto_start:
        install_autostart(launcher_command())

    if start_now:
        start_background_process(launcher_command())

    return (
        f"{APP_NAME} installed.\n"
        f"Config: {config_path()}\n"
        f"Auto-start: {'enabled' if config.auto_start else 'disabled'}\n"
        f"Agent name: {config.agent_name}"
    )


def uninstall_autostart() -> None:
    system = platform.system()
    if system == "Windows":
        _remove_windows_run_key()
    elif system == "Darwin":
        _remove_macos_launch_agent()
    else:
        _remove_linux_systemd_service()


def install_autostart(command: Sequence[str]) -> None:
    system = platform.system()
    if system == "Windows":
        _install_windows_run_key(command)
    elif system == "Darwin":
        _install_macos_launch_agent(command)
    else:
        _install_linux_systemd_service(command)


def start_background_process(command: Sequence[str]) -> None:
    kwargs = {"cwd": str(app_data_dir())}
    if platform.system() == "Windows":
        creationflags = 0x00000008 | 0x00000200
        subprocess.Popen(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
            **kwargs,
        )
    else:
        subprocess.Popen(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
            **kwargs,
        )


def _install_windows_run_key(command: Sequence[str]) -> None:
    import winreg

    value = subprocess.list2cmdline(list(command))
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, RUN_KEY_NAME, 0, winreg.REG_SZ, value)


def _remove_windows_run_key() -> None:
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_KEY_NAME)
    except FileNotFoundError:
        return


def _install_macos_launch_agent(command: Sequence[str]) -> None:
    path = mac_launch_agent_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": APP_BUNDLE_ID,
        "ProgramArguments": list(command),
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(app_data_dir()),
        "StandardOutPath": str(app_data_dir() / "stdout.log"),
        "StandardErrorPath": str(app_data_dir() / "stderr.log"),
    }

    with path.open("wb") as handle:
        plistlib.dump(payload, handle)

    target = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", target, str(path)], check=False)
    bootstrap = subprocess.run(["launchctl", "bootstrap", target, str(path)], check=False, capture_output=True, text=True)
    if bootstrap.returncode != 0:
        subprocess.run(["launchctl", "load", "-w", str(path)], check=True)
    else:
        subprocess.run(["launchctl", "enable", f"{target}/{APP_BUNDLE_ID}"], check=False)


def _remove_macos_launch_agent() -> None:
    path = mac_launch_agent_path()
    if not path.exists():
        return
    target = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", target, str(path)], check=False)
    subprocess.run(["launchctl", "unload", "-w", str(path)], check=False)
    path.unlink(missing_ok=True)


def _install_linux_systemd_service(command: Sequence[str]) -> None:
    path = linux_systemd_service_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        [
            "[Unit]",
            f"Description={APP_NAME}",
            "After=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={app_data_dir()}",
            f"ExecStart={shlex.join(list(command))}",
            "Restart=always",
            "RestartSec=5",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "--now", path.name], check=False)


def _remove_linux_systemd_service() -> None:
    path = linux_systemd_service_path()
    subprocess.run(["systemctl", "--user", "disable", "--now", path.name], check=False)
    path.unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
