from __future__ import annotations

from io import BytesIO
import hashlib
from pathlib import Path
import re
from typing import Any
import zipfile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.setting import AppSetting


class MemoryCoreService:
    PROFILE_PREFIX = "memorycore:profile"
    PROJECT_PREFIX = "memorycore:project"
    CONTEXT_CHAR_LIMIT = 1800
    STANDALONE_PLATFORMS = {
        "windows-x64": ("memorycore.exe", "exe"),
        "macos-arm64": ("memorycore", "unix"),
        "macos-x64": ("memorycore", "unix"),
    }

    @staticmethod
    def get_profile(db: Session, user_id: str) -> dict | None:
        record = db.scalar(select(AppSetting).where(AppSetting.key == MemoryCoreService._profile_key(user_id)))
        if record is None:
            return None
        return MemoryCoreService._serialize_profile(user_id, record)

    @staticmethod
    def upsert_profile(db: Session, user_id: str, payload: dict[str, Any]) -> dict:
        record = db.scalar(select(AppSetting).where(AppSetting.key == MemoryCoreService._profile_key(user_id)))
        current = dict(record.value_json or {}) if record is not None else {}
        merged = MemoryCoreService._normalize_profile_payload({**current, **payload})
        if record is None:
            record = AppSetting(key=MemoryCoreService._profile_key(user_id), value_json=merged)
            db.add(record)
        else:
            record.value_json = merged
        db.commit()
        db.refresh(record)
        return MemoryCoreService._serialize_profile(user_id, record)

    @staticmethod
    def list_projects(db: Session, user_id: str) -> list[dict]:
        prefix = MemoryCoreService._project_prefix(user_id)
        stmt = (
            select(AppSetting)
            .where(AppSetting.key.like(f"{prefix}%"))
            .order_by(AppSetting.updated_at.desc(), AppSetting.id.desc())
        )
        results: list[dict] = []
        for record in db.scalars(stmt).all():
            results.append(MemoryCoreService._serialize_project(user_id, record))
        return results

    @staticmethod
    def get_project(db: Session, user_id: str, project_key: str) -> dict | None:
        record = db.scalar(
            select(AppSetting).where(AppSetting.key == MemoryCoreService._project_key(user_id, project_key))
        )
        if record is None:
            return None
        return MemoryCoreService._serialize_project(user_id, record)

    @staticmethod
    def upsert_project(db: Session, user_id: str, project_key: str, payload: dict[str, Any]) -> dict:
        normalized_key = MemoryCoreService.normalize_project_key(project_key)
        record = db.scalar(
            select(AppSetting).where(AppSetting.key == MemoryCoreService._project_key(user_id, normalized_key))
        )
        current = dict(record.value_json or {}) if record is not None else {}
        merged = MemoryCoreService._normalize_project_payload(
            normalized_key,
            {
                **current,
                **payload,
            },
        )
        if record is None:
            record = AppSetting(
                key=MemoryCoreService._project_key(user_id, normalized_key),
                value_json=merged,
            )
            db.add(record)
        else:
            record.value_json = merged
        db.commit()
        db.refresh(record)
        return MemoryCoreService._serialize_project(user_id, record)

    @staticmethod
    def delete_project(db: Session, user_id: str, project_key: str) -> bool:
        record = db.scalar(
            select(AppSetting).where(AppSetting.key == MemoryCoreService._project_key(user_id, project_key))
        )
        if record is None:
            return False
        db.delete(record)
        db.commit()
        return True

    @staticmethod
    def delete_profile(db: Session, user_id: str) -> bool:
        record = db.scalar(select(AppSetting).where(AppSetting.key == MemoryCoreService._profile_key(user_id)))
        if record is None:
            return False
        db.delete(record)
        db.commit()
        return True

    @staticmethod
    def delete_all_projects(db: Session, user_id: str) -> int:
        prefix = MemoryCoreService._project_prefix(user_id)
        records = list(
            db.scalars(
                select(AppSetting).where(AppSetting.key.like(f"{prefix}%"))
            ).all()
        )
        count = len(records)
        for record in records:
            db.delete(record)
        db.commit()
        return count

    @staticmethod
    def clear_all(db: Session, user_id: str) -> dict[str, int]:
        deleted_profile = 1 if MemoryCoreService.delete_profile(db, user_id) else 0
        deleted_projects = MemoryCoreService.delete_all_projects(db, user_id)
        return {
            "deleted_profile": deleted_profile,
            "deleted_projects": deleted_projects,
        }

    @staticmethod
    def build_launcher_bundle(*, server_url: str, user_id: str, wake_name: str, platform: str) -> tuple[str, bytes]:
        normalized_wake = MemoryCoreService.normalize_project_key(wake_name or "jarvis")
        project_root = Path(__file__).resolve().parents[2]
        binary_name, launcher_kind = MemoryCoreService.STANDALONE_PLATFORMS.get(platform, ("", ""))
        if not binary_name:
            raise ValueError(f"Unsupported MemoryCore platform `{platform}`.")
        binary_path = project_root / "memorycore_dist" / platform / binary_name
        if not binary_path.exists():
            raise FileNotFoundError(f"MemoryCore binary is not available for `{platform}` yet.")
        binary_bytes = binary_path.read_bytes()
        packaged_binary_name = "memorycore-bin.exe" if launcher_kind == "exe" else "memorycore-bin"

        bundle_name = f"memorycore-{platform}-{normalized_wake}"
        readme = MemoryCoreService._render_launcher_readme(
            server_url=server_url,
            user_id=user_id,
            wake_name=normalized_wake,
            platform=platform,
        )

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("README.txt", readme)
            if launcher_kind == "exe":
                archive.writestr(packaged_binary_name, binary_bytes)
                archive.writestr(
                    "memorycore.cmd",
                    MemoryCoreService._render_windows_launcher(
                        "memorycore",
                        server_url,
                        user_id,
                        normalized_wake,
                        packaged_binary_name=packaged_binary_name,
                        expect_wake=False,
                    ),
                )
                archive.writestr(
                    "hey.cmd",
                    MemoryCoreService._render_windows_launcher(
                        "hey",
                        server_url,
                        user_id,
                        normalized_wake,
                        packaged_binary_name=packaged_binary_name,
                        expect_wake=True,
                    ),
                )
                archive.writestr(
                    f"{normalized_wake}.cmd",
                    MemoryCoreService._render_windows_launcher(
                        normalized_wake,
                        server_url,
                        user_id,
                        normalized_wake,
                        packaged_binary_name=packaged_binary_name,
                        expect_wake=False,
                    ),
                )
                archive.writestr(
                    "Install MemoryCore.cmd",
                    MemoryCoreService._render_windows_install_helper(
                        packaged_binary_name=packaged_binary_name,
                        wake_name=normalized_wake,
                    ),
                )
            else:
                MemoryCoreService._write_zip_entry(archive, packaged_binary_name, binary_bytes, 0o755)
                MemoryCoreService._write_zip_entry(
                    archive,
                    "memorycore",
                    MemoryCoreService._render_unix_launcher(
                        "memorycore",
                        server_url,
                        user_id,
                        normalized_wake,
                        packaged_binary_name=packaged_binary_name,
                        expect_wake=False,
                    ).encode("utf-8"),
                    0o755,
                )
                MemoryCoreService._write_zip_entry(
                    archive,
                    "hey",
                    MemoryCoreService._render_unix_launcher(
                        "hey",
                        server_url,
                        user_id,
                        normalized_wake,
                        packaged_binary_name=packaged_binary_name,
                        expect_wake=True,
                    ).encode("utf-8"),
                    0o755,
                )
                MemoryCoreService._write_zip_entry(
                    archive,
                    normalized_wake,
                    MemoryCoreService._render_unix_launcher(
                        normalized_wake,
                        server_url,
                        user_id,
                        normalized_wake,
                        packaged_binary_name=packaged_binary_name,
                        expect_wake=False,
                    ).encode("utf-8"),
                    0o755,
                )
                MemoryCoreService._write_zip_entry(
                    archive,
                    "Install MemoryCore.command",
                    MemoryCoreService._render_unix_install_helper(
                        packaged_binary_name=packaged_binary_name,
                        wake_name=normalized_wake,
                    ).encode("utf-8"),
                    0o755,
                )

        return f"{bundle_name}.zip", buffer.getvalue()

    @staticmethod
    def render_project_markdown(db: Session, user_id: str, project_key: str) -> str | None:
        project = MemoryCoreService.get_project(db, user_id=user_id, project_key=project_key)
        if project is None:
            return None
        profile = MemoryCoreService.get_profile(db, user_id=user_id)
        return MemoryCoreService.render_markdown(profile=profile, project=project)

    @staticmethod
    def render_markdown(profile: dict | None, project: dict) -> str:
        lines = [
            f"# MemoryCore: {project['title']}",
            "",
            f"- Project key: `{project['project_key']}`",
            f"- Updated: {project['updated_at'].isoformat()}",
        ]
        if project.get("root_hint"):
            lines.append(f"- Local path hint: `{project['root_hint']}`")
        if project.get("repo_origin"):
            lines.append(f"- Repo origin: `{project['repo_origin']}`")

        if project.get("summary"):
            lines.extend(["", "## Project Summary", "", project["summary"]])

        lines.extend(MemoryCoreService._render_section("Goals", project.get("goals", [])))
        lines.extend(MemoryCoreService._render_section("Stack", project.get("stack", [])))
        lines.extend(MemoryCoreService._render_section("Important Files", project.get("important_files", []), code=True))
        lines.extend(MemoryCoreService._render_section("Useful Commands", project.get("commands", []), code=True))
        lines.extend(MemoryCoreService._render_section("Project Structure", project.get("structure", []), code=True))
        lines.extend(MemoryCoreService._render_section("Project Preferences", project.get("preferences", [])))
        lines.extend(MemoryCoreService._render_section("Project Notes", project.get("notes", [])))

        if profile:
            lines.extend(["", "## User Memory Profile", ""])
            if profile.get("display_name"):
                lines.append(f"- Name: {profile['display_name']}")
            if profile.get("about"):
                lines.append(f"- About: {profile['about']}")
            lines.extend(MemoryCoreService._render_section("General Preferences", profile.get("preferences", [])))
            lines.extend(MemoryCoreService._render_section("Coding Preferences", profile.get("coding_preferences", [])))
            lines.extend(MemoryCoreService._render_section("Workflow Preferences", profile.get("workflow_preferences", [])))
            lines.extend(MemoryCoreService._render_section("Persistent Notes", profile.get("notes", [])))

        lines.extend(
            [
                "",
                "## How To Use This",
                "",
                "- Use this file as standing context for new Codex or Claude Code sessions.",
                "- Keep it concise and update it when the project structure or preferences change.",
                "- The server copy is the source of truth; regenerate this file whenever you pull the latest memory.",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def build_assistant_context(db: Session, user_id: str, project_key: str | None = None) -> str:
        profile = MemoryCoreService.get_profile(db, user_id=user_id)
        project = MemoryCoreService.get_project(db, user_id=user_id, project_key=project_key) if project_key else None

        sections: list[str] = []
        if profile:
            sections.append("User preferences:")
            for item in profile.get("preferences", [])[:6]:
                sections.append(f"- {item}")
            for item in profile.get("coding_preferences", [])[:6]:
                sections.append(f"- Coding: {item}")
            for item in profile.get("workflow_preferences", [])[:4]:
                sections.append(f"- Workflow: {item}")

        if project:
            sections.append(f"Current project: {project['title']} (`{project['project_key']}`)")
            if project.get("summary"):
                sections.append(f"- Summary: {project['summary']}")
            for item in project.get("stack", [])[:6]:
                sections.append(f"- Stack: {item}")
            for item in project.get("preferences", [])[:6]:
                sections.append(f"- Project pref: {item}")
            for item in project.get("important_files", [])[:8]:
                sections.append(f"- Important file: {item}")

        text = "\n".join(sections).strip()
        if len(text) > MemoryCoreService.CONTEXT_CHAR_LIMIT:
            return text[: MemoryCoreService.CONTEXT_CHAR_LIMIT].rstrip() + "..."
        return text

    @staticmethod
    def normalize_project_key(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
        return slug or "project"

    @staticmethod
    def _render_section(title: str, items: list[str], *, code: bool = False) -> list[str]:
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        if not cleaned:
            return []
        lines = ["", f"## {title}", ""]
        for item in cleaned:
            lines.append(f"- `{item}`" if code else f"- {item}")
        return lines

    @staticmethod
    def _serialize_profile(user_id: str, record: AppSetting) -> dict:
        payload = MemoryCoreService._normalize_profile_payload(dict(record.value_json or {}))
        return {
            "user_id": user_id,
            **payload,
            "updated_at": record.updated_at,
        }

    @staticmethod
    def _serialize_project(user_id: str, record: AppSetting) -> dict:
        payload = MemoryCoreService._normalize_project_payload(
            str((record.value_json or {}).get("project_key") or "project"),
            dict(record.value_json or {}),
        )
        return {
            "user_id": user_id,
            **payload,
            "updated_at": record.updated_at,
        }

    @staticmethod
    def _normalize_profile_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "display_name": MemoryCoreService._clean_text(payload.get("display_name")),
            "about": MemoryCoreService._clean_text(payload.get("about")),
            "preferences": MemoryCoreService._clean_list(payload.get("preferences")),
            "coding_preferences": MemoryCoreService._clean_list(payload.get("coding_preferences")),
            "workflow_preferences": MemoryCoreService._clean_list(payload.get("workflow_preferences")),
            "notes": MemoryCoreService._clean_list(payload.get("notes")),
            "tags": MemoryCoreService._clean_list(payload.get("tags")),
            "schema_version": 1,
        }

    @staticmethod
    def _normalize_project_payload(project_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        title = MemoryCoreService._clean_text(payload.get("title")) or project_key.replace("-", " ").title()
        return {
            "project_key": MemoryCoreService.normalize_project_key(project_key),
            "title": title,
            "summary": MemoryCoreService._clean_text(payload.get("summary")) or "",
            "root_hint": MemoryCoreService._clean_text(payload.get("root_hint")),
            "repo_origin": MemoryCoreService._clean_text(payload.get("repo_origin")),
            "stack": MemoryCoreService._clean_list(payload.get("stack")),
            "goals": MemoryCoreService._clean_list(payload.get("goals")),
            "important_files": MemoryCoreService._clean_list(payload.get("important_files")),
            "commands": MemoryCoreService._clean_list(payload.get("commands")),
            "structure": MemoryCoreService._clean_list(payload.get("structure")),
            "preferences": MemoryCoreService._clean_list(payload.get("preferences")),
            "notes": MemoryCoreService._clean_list(payload.get("notes")),
            "tags": MemoryCoreService._clean_list(payload.get("tags")),
            "schema_version": 1,
        }

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _clean_list(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        results: list[str] = []
        seen: set[str] = set()
        for item in values:
            text = str(item or "").strip()
            lowered = text.lower()
            if not text or lowered in seen:
                continue
            seen.add(lowered)
            results.append(text)
        return results[:80]

    @staticmethod
    def _profile_key(user_id: str) -> str:
        return f"{MemoryCoreService.PROFILE_PREFIX}:{MemoryCoreService._user_token(user_id)}"

    @staticmethod
    def _project_prefix(user_id: str) -> str:
        return f"{MemoryCoreService.PROJECT_PREFIX}:{MemoryCoreService._user_token(user_id)}:"

    @staticmethod
    def _project_key(user_id: str, project_key: str) -> str:
        normalized = MemoryCoreService.normalize_project_key(project_key)
        return f"{MemoryCoreService._project_prefix(user_id)}{MemoryCoreService._project_token(normalized)}"

    @staticmethod
    def _user_token(user_id: str) -> str:
        return hashlib.sha1(user_id.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _project_token(project_key: str) -> str:
        return hashlib.sha1(project_key.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _render_launcher_readme(*, server_url: str, user_id: str, wake_name: str, platform: str) -> str:
        mac_install = (
            "macOS:\n"
            "1. Extract the zip somewhere convenient.\n"
            "2. Double-click `Install MemoryCore.command`.\n"
            f"3. Reopen Terminal, then run `{wake_name} remember this whole thing` or `hey {wake_name} remember this whole thing`.\n"
            "4. If you prefer portable mode, run `chmod +x memorycore memorycore-bin hey "
            f"{wake_name} \"Install MemoryCore.command\"` and use the extracted folder directly.\n\n"
        )
        windows_install = (
            "Windows:\n"
            "1. Extract the zip somewhere simple.\n"
            "2. Double-click `Install MemoryCore.cmd`.\n"
            f"3. Reopen PowerShell or Command Prompt, then run `{wake_name} remember this whole thing` or `hey {wake_name} remember this whole thing`.\n"
            "4. If you prefer portable mode, you can also run the `.cmd` launchers from the extracted folder directly.\n\n"
        )
        return (
            "MemoryCore Standalone Bundle\n"
            "===========================\n\n"
            f"Server URL: {server_url}\n"
            f"User ID: {user_id}\n"
            f"Wake name: {wake_name}\n\n"
            f"Bundle platform: {platform}\n\n"
            f"{windows_install if platform == 'windows-x64' else mac_install}"
            "Behavior:\n"
            "- `remember this whole thing` saves the project memory to the server.\n"
            "- It also writes a local `MEMORYCORE.md` into the current project folder by default.\n"
            "- Use the matching wake name from this bundle when you type the command.\n"
        )

    @staticmethod
    def _render_windows_launcher(
        script_name: str,
        server_url: str,
        user_id: str,
        wake_name: str,
        *,
        packaged_binary_name: str,
        expect_wake: bool,
    ) -> str:
        escaped_server = server_url.replace('"', '""')
        escaped_user = user_id.replace('"', '""')
        escaped_wake = wake_name.replace('"', '""')
        escaped_binary = packaged_binary_name.replace('"', '""')
        if expect_wake:
            usage = f"echo Usage: hey {escaped_wake} remember this whole thing"
            wake_parse = (
                "if \"%~1\"==\"\" goto usage\r\n"
                f"if /I not \"%~1\"==\"{escaped_wake}\" (\r\n"
                f"  echo Wake name mismatch. Expected {escaped_wake}.\r\n"
                "  exit /b 1\r\n"
                ")\r\n"
                "shift\r\n"
            )
        else:
            usage = f"echo Usage: {script_name} remember this whole thing"
            wake_parse = "if \"%~1\"==\"\" goto usage\r\n"
        return (
            "@echo off\r\n"
            "setlocal\r\n"
            "set SCRIPT_DIR=%~dp0\r\n"
            f"set SERVER_URL={escaped_server}\r\n"
            f"set MEMORYCORE_USER={escaped_user}\r\n"
            f"set WAKE_NAME={escaped_wake}\r\n"
            f"{wake_parse}"
            "goto run\r\n"
            ":usage\r\n"
            f"{usage}\r\n"
            "exit /b 1\r\n"
            ":run\r\n"
            f"\"%SCRIPT_DIR%{escaped_binary}\" --server-url \"%SERVER_URL%\" --user-id \"%MEMORYCORE_USER%\" %*\r\n"
        )

    @staticmethod
    def _render_unix_launcher(
        script_name: str,
        server_url: str,
        user_id: str,
        wake_name: str,
        *,
        packaged_binary_name: str,
        expect_wake: bool,
    ) -> str:
        if expect_wake:
            usage = f'echo "Usage: hey {wake_name} remember this whole thing"'
            wake_parse = (
                'if [ $# -lt 1 ]; then\n'
                "  goto_usage=1\n"
                "elif [ \"$1\" != \"$WAKE_NAME\" ]; then\n"
                '  echo "Wake name mismatch. Expected $WAKE_NAME."\n'
                "  exit 1\n"
                "else\n"
                "  shift\n"
                "fi\n"
            )
        else:
            usage = f'echo "Usage: {script_name} remember this whole thing"'
            wake_parse = (
                'if [ $# -lt 1 ]; then\n'
                "  goto_usage=1\n"
                "fi\n"
            )
        return (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n\n"
            'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
            f'SERVER_URL="{server_url}"\n'
            f'MEMORYCORE_USER="{user_id}"\n'
            f'WAKE_NAME="{wake_name}"\n'
            "goto_usage=0\n"
            f"{wake_parse}"
            'if [ "$goto_usage" = "1" ]; then\n'
            f"  {usage}\n"
            "  exit 1\n"
            "fi\n\n"
            f'"$SCRIPT_DIR/{packaged_binary_name}" --server-url "$SERVER_URL" --user-id "$MEMORYCORE_USER" "$@"\n'
        )

    @staticmethod
    def _write_zip_entry(archive: zipfile.ZipFile, filename: str, content: bytes, mode: int) -> None:
        info = zipfile.ZipInfo(filename)
        info.create_system = 3
        info.external_attr = mode << 16
        archive.writestr(info, content)

    @staticmethod
    def _render_windows_install_helper(*, packaged_binary_name: str, wake_name: str) -> str:
        escaped_binary = packaged_binary_name.replace('"', '""')
        escaped_wake = wake_name.replace('"', '""')
        return (
            "@echo off\r\n"
            "setlocal\r\n"
            "set SCRIPT_DIR=%~dp0\r\n"
            "set TARGET_DIR=%LOCALAPPDATA%\\Programs\\MemoryCore\r\n"
            "if not exist \"%TARGET_DIR%\" mkdir \"%TARGET_DIR%\"\r\n"
            f"copy /Y \"%SCRIPT_DIR%{escaped_binary}\" \"%TARGET_DIR%\\{escaped_binary}\" >nul\r\n"
            "copy /Y \"%SCRIPT_DIR%memorycore.cmd\" \"%TARGET_DIR%\\memorycore.cmd\" >nul\r\n"
            "copy /Y \"%SCRIPT_DIR%hey.cmd\" \"%TARGET_DIR%\\hey.cmd\" >nul\r\n"
            f"copy /Y \"%SCRIPT_DIR%{escaped_wake}.cmd\" \"%TARGET_DIR%\\{escaped_wake}.cmd\" >nul\r\n"
            "copy /Y \"%SCRIPT_DIR%README.txt\" \"%TARGET_DIR%\\README.txt\" >nul\r\n"
            "powershell -NoProfile -ExecutionPolicy Bypass -Command "
            "\"$target = Join-Path $env:LOCALAPPDATA 'Programs\\MemoryCore'; "
            "$current = [Environment]::GetEnvironmentVariable('Path', 'User'); "
            "if ([string]::IsNullOrWhiteSpace($current)) { $parts = @() } else { $parts = $current -split ';' | Where-Object { $_ } }; "
            "$normalizedTarget = $target.TrimEnd('\\\\'); "
            "$exists = $false; "
            "foreach ($part in $parts) { if ($part.Trim().TrimEnd('\\\\') -ieq $normalizedTarget) { $exists = $true; break } }; "
            "if (-not $exists) { "
            "$newValue = @($parts + $target) -join ';'; "
            "[Environment]::SetEnvironmentVariable('Path', $newValue, 'User') }\"\r\n"
            "echo.\r\n"
            "echo MemoryCore was installed to %TARGET_DIR%.\r\n"
            f"echo Reopen your terminal, then run {escaped_wake} remember this whole thing\r\n"
            f"echo or hey {escaped_wake} remember this whole thing\r\n"
            "pause\r\n"
        )

    @staticmethod
    def _render_unix_install_helper(*, packaged_binary_name: str, wake_name: str) -> str:
        return (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n\n"
            'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
            'INSTALL_ROOT="$HOME/.local/share/memorycore"\n'
            'BIN_DIR="$HOME/.local/bin"\n'
            'mkdir -p "$INSTALL_ROOT" "$BIN_DIR"\n'
            f'cp "$SCRIPT_DIR/{packaged_binary_name}" "$INSTALL_ROOT/{packaged_binary_name}"\n'
            'cp "$SCRIPT_DIR/memorycore" "$BIN_DIR/memorycore"\n'
            'cp "$SCRIPT_DIR/hey" "$BIN_DIR/hey"\n'
            f'cp "$SCRIPT_DIR/{wake_name}" "$BIN_DIR/{wake_name}"\n'
            'cp "$SCRIPT_DIR/README.txt" "$INSTALL_ROOT/README.txt"\n'
            f'chmod +x "$INSTALL_ROOT/{packaged_binary_name}" "$BIN_DIR/memorycore" "$BIN_DIR/hey" "$BIN_DIR/{wake_name}"\n'
            '\n'
            'PATH_LINE=\'export PATH="$HOME/.local/bin:$PATH"\'\n'
            'for shell_rc in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bashrc"; do\n'
            '  if [ ! -f "$shell_rc" ]; then\n'
            '    touch "$shell_rc"\n'
            '  fi\n'
            '  if ! grep -Fq "$PATH_LINE" "$shell_rc"; then\n'
            '    printf \'\\n%s\\n\' "$PATH_LINE" >> "$shell_rc"\n'
            '  fi\n'
            'done\n'
            '\n'
            'echo\n'
            'echo "MemoryCore was installed into ~/.local/bin and ~/.local/share/memorycore."\n'
            f'echo "Reopen Terminal, then run {wake_name} remember this whole thing"\n'
            f'echo "or hey {wake_name} remember this whole thing"\n'
        )
