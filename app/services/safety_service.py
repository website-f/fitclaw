from __future__ import annotations

import re


class SafetyService:
    CHAT_DESTRUCTIVE_PATTERN = re.compile(
        r"\b(delete|remove|erase|wipe|format|move|rename|kill|terminate|shutdown|restart)\b.*\b(agent|device|pc|computer|file|folder|directory|drive|process|service)\b|"
        r"\b(run|execute)\b.*\b(shell|powershell|cmd|terminal|script|command)\b.*\b(on|against|for)\b.*\b(agent|device|pc|computer)\b",
        re.IGNORECASE,
    )
    CONTROL_ONLY_COMMANDS = {
        "mouse_move",
        "mouse_click",
        "mouse_drag",
        "keyboard_type",
        "keyboard_hotkey",
        "keyboard_press",
        "window_focus",
    }
    MUTATING_COMMANDS = {"file_delete", "file_write", "process_kill", "app_launch"}
    HIGH_RISK_APP_ACTIONS = {"codex_exec", "vscode_codex_prompt", "vscode_open_path"}

    @staticmethod
    def chat_policy_warning(text: str) -> str | None:
        if not text.strip():
            return None
        if not SafetyService.CHAT_DESTRUCTIVE_PATTERN.search(text):
            return None
        return (
            "I won't run destructive or direct shell-style device actions from chat.\n\n"
            "Use `/control` for anything that deletes, moves, kills, rewrites, or directly drives a machine. "
            "That keeps agents from removing or changing things unless you explicitly do it from the control panel."
        )

    @staticmethod
    def validate_control_command(command_type: str, payload_json: dict, source: str) -> None:
        normalized_type = command_type.strip().lower()
        normalized_source = source.strip().lower()
        payload = payload_json or {}
        approval_confirmed = bool(payload.get("approval_confirmed"))

        if normalized_type in SafetyService.CONTROL_ONLY_COMMANDS and normalized_source != "control_panel":
            raise ValueError(f"`{normalized_type}` can only be issued from /control.")

        if normalized_type in SafetyService.MUTATING_COMMANDS:
            if normalized_source != "control_panel":
                raise ValueError(f"`{normalized_type}` can only be issued from /control.")
            if not approval_confirmed:
                raise ValueError(f"`{normalized_type}` requires an explicit warning confirmation in /control.")

        if normalized_type == "app_action":
            action = str(payload.get("action", "")).strip().lower()
            if action in {"browser_open_url", "file_manager_reveal"} and normalized_source != "control_panel":
                raise ValueError(f"`{action}` can only be issued from /control.")
            if action in SafetyService.HIGH_RISK_APP_ACTIONS:
                if normalized_source not in {"control_panel", "chat_approved"}:
                    raise ValueError(f"`{action}` requires a confirmed /control or chat approval flow.")
                if not approval_confirmed:
                    raise ValueError(f"`{action}` requires an explicit warning confirmation before it can run.")
