from __future__ import annotations

from datetime import datetime, timezone
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
    SESSION_LINK_PREFIX = "memorycore:session-link"
    CONTEXT_CHAR_LIMIT = 1800
    ACTIVITY_LOG_LIMIT = 24
    PROJECT_STATUSES = {"active", "archived"}
    STANDALONE_PLATFORMS = {
        "windows-x64": ("memorycore.exe", "exe"),
        "macos-arm64": ("memorycore", "unix"),
        "macos-x64": ("memorycore", "unix"),
    }
    LIBRARY_TEMPLATES = {
        "project-kickoff": {
            "title": "Project Kickoff",
            "category": "planning",
            "summary": "Sets up a clean kickoff layer with scope, constraints, milestones, and the first decision checkpoints.",
            "current_focus": "Clarify the scope, success criteria, and first milestone before implementation accelerates.",
            "session_brief": "Use this kickoff memory to keep the project grounded on scope, outcomes, and the next concrete milestone.",
            "library_items": [
                "Kickoff scope statement",
                "Success criteria checklist",
                "Known constraints and non-goals",
                "First milestone and handoff definition",
            ],
            "next_steps": [
                "Write a short scope statement for the project.",
                "Capture fixed deadlines, constraints, and non-goals.",
                "Define the first milestone and who signs it off.",
            ],
            "open_questions": [
                "What does done look like for the first milestone?",
                "Which assumptions still need validation?",
                "Who are the decision-makers and reviewers for this project?",
            ],
            "observations": [
                "Kickoff memories are most useful when they stay short and get updated after major scope decisions.",
            ],
            "skills": [
                "Start new sessions by reviewing scope, milestone, and open questions before coding.",
            ],
        },
        "session-briefing": {
            "title": "Session Briefing",
            "category": "workflow",
            "summary": "Adds a compact briefing structure so every new session can restart quickly without re-scanning the whole repo.",
            "current_focus": "Keep the next session restartable with a tight briefing, live focus, and a handoff-quality next-step list.",
            "session_brief": "Begin by reading the current focus, top next steps, recent decisions, and any blockers before continuing work.",
            "library_items": [
                "Session-start briefing format",
                "Handoff recap template",
                "Blockers and assumptions tracker",
            ],
            "next_steps": [
                "Summarize the current focus in one paragraph.",
                "Keep the top three next steps updated after each work block.",
                "Record blockers or assumptions when they appear.",
            ],
            "reminders": [
                "Refresh the briefing whenever the project direction changes noticeably.",
            ],
            "decisions": [
                "Use the Memory Core briefing as the first orientation layer for new chats.",
            ],
            "skills": [
                "Start each session by reviewing briefing, next steps, reminders, and recent changes.",
            ],
        },
        "debugging-incident": {
            "title": "Debugging Incident",
            "category": "engineering",
            "summary": "Creates a reproducible debugging memory with hypotheses, evidence, failure scope, and rollback notes.",
            "current_focus": "Pin down the failure scope, strongest hypothesis, and the smallest reproducible path.",
            "session_brief": "Treat this as an incident log: keep the repro path, tested hypotheses, and confirmed evidence current.",
            "library_items": [
                "Minimal reproduction steps",
                "Failure scope and impacted surfaces",
                "Evidence log and hypothesis tracker",
                "Rollback or mitigation notes",
            ],
            "next_steps": [
                "Write the smallest reproducible path.",
                "List the top hypotheses in descending confidence order.",
                "Capture evidence that confirms or rejects each hypothesis.",
            ],
            "open_questions": [
                "What changed shortly before the failure appeared?",
                "What user-facing behavior is actually broken versus only degraded?",
                "What is the safest rollback or mitigation if the fix slips?",
            ],
            "observations": [
                "Debugging memories work best when hypothesis changes are logged explicitly instead of implied.",
            ],
            "skills": [
                "Prefer evidence-driven debugging over broad speculative changes.",
            ],
        },
        "ui-polish": {
            "title": "UI Polish",
            "category": "design",
            "summary": "Focuses the memory on UX refinement, visual consistency, responsive behavior, and review loops.",
            "current_focus": "Improve the interface with sharper hierarchy, stronger responsiveness, and more intentional visual polish.",
            "session_brief": "Keep the UI review grounded on user flow, hierarchy, responsiveness, and finish quality instead of isolated tweaks.",
            "library_items": [
                "Primary user flow checkpoints",
                "Responsive layout review checklist",
                "Typography and spacing consistency notes",
                "Interaction polish and edge-case states",
            ],
            "next_steps": [
                "List the most important user flows to verify visually.",
                "Record responsive issues on mobile and desktop separately.",
                "Capture any weak states, loading screens, or empty states that still need polish.",
            ],
            "observations": [
                "UI memory is stronger when it stores screenshots, edge cases, and exact interaction issues rather than vague taste notes.",
            ],
            "skills": [
                "Review hierarchy, spacing, states, and responsive behavior before shipping design tweaks.",
            ],
        },
        "handoff-readiness": {
            "title": "Handoff Readiness",
            "category": "delivery",
            "summary": "Prepares a project for continuation by another session, teammate, or machine with clear runbooks and unresolved risks.",
            "current_focus": "Make the project restartable by someone else with minimal hidden context.",
            "session_brief": "Optimize this memory for continuation: what changed, what is left, how to run it, and where the risks still are.",
            "library_items": [
                "Run and verify checklist",
                "Known risks and sharp edges",
                "Deployment or release notes",
                "Who owns the next decision",
            ],
            "next_steps": [
                "Write the exact run and verification steps.",
                "List unfinished work with clear ownership or next decision points.",
                "Capture any risky areas that need extra review before release.",
            ],
            "reminders": [
                "Update handoff notes before switching machines or ending a session.",
            ],
            "decisions": [
                "Treat restartability as a first-class quality bar for long-running projects.",
            ],
            "skills": [
                "Write handoff notes as if the next session has zero hidden context.",
            ],
        },
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
        results = [MemoryCoreService._serialize_project(user_id, record) for record in db.scalars(stmt).all()]
        return sorted(results, key=MemoryCoreService._project_sort_key)

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
        detail = MemoryCoreService._summarize_project_save(current=current, merged=merged, created=record is None)
        merged["activity_log"] = MemoryCoreService._append_activity_event(
            current.get("activity_log"),
            kind="created" if record is None else "saved",
            detail=detail,
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
    def touch_project(db: Session, user_id: str, project_key: str) -> dict | None:
        record = db.scalar(
            select(AppSetting).where(AppSetting.key == MemoryCoreService._project_key(user_id, project_key))
        )
        if record is None:
            return None
        payload = dict(record.value_json or {})
        payload["last_opened_at"] = datetime.now(timezone.utc).isoformat()
        payload["open_count"] = MemoryCoreService._clean_int(payload.get("open_count"), minimum=0) + 1
        payload["activity_log"] = MemoryCoreService._append_activity_event(
            payload.get("activity_log"),
            kind="opened",
            detail=f"Opened project memory ({payload['open_count']} total opens).",
        )
        record.value_json = MemoryCoreService._normalize_project_payload(
            str(payload.get("project_key") or project_key),
            payload,
        )
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
    def delete_all_session_links(db: Session, user_id: str) -> int:
        prefix = MemoryCoreService._session_link_prefix(user_id)
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
        deleted_session_links = MemoryCoreService.delete_all_session_links(db, user_id)
        return {
            "deleted_profile": deleted_profile,
            "deleted_projects": deleted_projects,
            "deleted_session_links": deleted_session_links,
        }

    @staticmethod
    def list_library_templates() -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for template_key, template in MemoryCoreService.LIBRARY_TEMPLATES.items():
            results.append(
                {
                    "template_key": template_key,
                    "title": template["title"],
                    "category": template["category"],
                    "summary": template["summary"],
                    "current_focus": template.get("current_focus"),
                    "session_brief": template.get("session_brief"),
                    "library_items": list(template.get("library_items", [])),
                    "next_steps": list(template.get("next_steps", [])),
                    "reminders": list(template.get("reminders", [])),
                    "decisions": list(template.get("decisions", [])),
                    "observations": list(template.get("observations", [])),
                    "open_questions": list(template.get("open_questions", [])),
                    "skills": list(template.get("skills", [])),
                }
            )
        return results

    @staticmethod
    def get_library_template(template_key: str) -> dict[str, Any] | None:
        normalized = MemoryCoreService.normalize_project_key(template_key)
        template = MemoryCoreService.LIBRARY_TEMPLATES.get(normalized)
        if template is None:
            return None
        return next(
            (item for item in MemoryCoreService.list_library_templates() if item["template_key"] == normalized),
            None,
        )

    @staticmethod
    def apply_library_template(db: Session, user_id: str, project_key: str, template_key: str) -> dict | None:
        project = MemoryCoreService.get_project(db, user_id=user_id, project_key=project_key)
        template = MemoryCoreService.get_library_template(template_key)
        if project is None or template is None:
            return None

        payload: dict[str, Any] = {}
        for field in ("library_items", "next_steps", "reminders", "decisions", "observations", "open_questions", "skills"):
            payload[field] = MemoryCoreService._merge_unique_lists(project.get(field, []), template.get(field, []))

        if not project.get("current_focus") and template.get("current_focus"):
            payload["current_focus"] = template["current_focus"]
        if not project.get("session_brief") and template.get("session_brief"):
            payload["session_brief"] = template["session_brief"]

        updated = MemoryCoreService.upsert_project(
            db,
            user_id=user_id,
            project_key=project["project_key"],
            payload=payload,
        )
        updated = MemoryCoreService._append_project_activity(
            db,
            user_id=user_id,
            project_key=project["project_key"],
            kind="template",
            detail=f"Applied Memory Core template `{template['title']}`.",
        ) or updated
        return updated

    @staticmethod
    def link_session_to_project(db: Session, user_id: str, session_id: str, project_key: str) -> None:
        normalized_project_key = MemoryCoreService.normalize_project_key(project_key)
        key = MemoryCoreService._session_link_key(user_id, session_id)
        record = db.scalar(select(AppSetting).where(AppSetting.key == key))
        payload = {
            "session_id": session_id,
            "project_key": normalized_project_key,
            "linked_at": datetime.now(timezone.utc).isoformat(),
        }
        if record is None:
            record = AppSetting(key=key, value_json=payload)
            db.add(record)
        else:
            record.value_json = payload
        db.commit()

    @staticmethod
    def get_linked_project_key(db: Session, user_id: str, session_id: str) -> str | None:
        key = MemoryCoreService._session_link_key(user_id, session_id)
        record = db.scalar(select(AppSetting).where(AppSetting.key == key))
        if record is None:
            return None
        project_key = str((record.value_json or {}).get("project_key", "")).strip()
        return project_key or None

    @staticmethod
    def capture_session_context(
        db: Session,
        *,
        user_id: str,
        project_key: str,
        session_id: str,
        limit: int = 80,
    ) -> dict | None:
        from app.services.memory_service import MemoryService

        project = MemoryCoreService.get_project(db, user_id=user_id, project_key=project_key)
        if project is None:
            return None

        messages = MemoryService.list_session_messages(
            db,
            session_id=session_id,
            platform_user_id=user_id,
            limit=max(limit, 12),
        )
        if not messages:
            MemoryCoreService.link_session_to_project(db, user_id=user_id, session_id=session_id, project_key=project_key)
            return project

        extracted = MemoryCoreService._extract_conversation_memory(messages)
        payload: dict[str, Any] = {
            "conversation_summary": extracted["conversation_summary"],
            "conversation_memory": extracted["conversation_memory"],
            "linked_sessions": MemoryCoreService._merge_unique_lists(project.get("linked_sessions", []), [session_id]),
        }

        for field in (
            "decisions",
            "next_steps",
            "open_questions",
            "recent_changes",
            "observations",
            "important_files",
            "commands",
        ):
            payload[field] = MemoryCoreService._merge_unique_lists(project.get(field, []), extracted.get(field, []))

        if extracted.get("current_focus"):
            payload["current_focus"] = extracted["current_focus"]
        if extracted.get("conversation_summary"):
            payload["session_brief"] = extracted["conversation_summary"]

        updated = MemoryCoreService.upsert_project(
            db,
            user_id=user_id,
            project_key=project["project_key"],
            payload=payload,
        )
        MemoryCoreService.link_session_to_project(db, user_id=user_id, session_id=session_id, project_key=project_key)
        updated = MemoryCoreService._append_project_activity(
            db,
            user_id=user_id,
            project_key=project["project_key"],
            kind="conversation",
            detail=f"Captured chat context from session `{session_id}`.",
        ) or updated
        return updated

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
            f"- Status: {project.get('status', 'active')}",
            f"- Updated: {project['updated_at'].isoformat()}",
        ]
        if project.get("last_opened_at"):
            lines.append(f"- Last opened: {project['last_opened_at'].isoformat()}")
        if project.get("open_count"):
            lines.append(f"- Times opened: {project['open_count']}")
        if project.get("root_hint"):
            lines.append(f"- Local path hint: `{project['root_hint']}`")
        if project.get("repo_origin"):
            lines.append(f"- Repo origin: `{project['repo_origin']}`")

        if project.get("summary"):
            lines.extend(["", "## Project Summary", "", project["summary"]])
        if project.get("session_brief"):
            lines.extend(["", "## Session Briefing", "", project["session_brief"]])
        if project.get("current_focus"):
            lines.extend(["", "## Current Focus", "", project["current_focus"]])
        if project.get("conversation_summary"):
            lines.extend(["", "## Conversation Summary", "", project["conversation_summary"]])

        lines.extend(MemoryCoreService._render_section("Goals", project.get("goals", [])))
        lines.extend(MemoryCoreService._render_section("Next Steps", project.get("next_steps", [])))
        lines.extend(MemoryCoreService._render_section("Reminders", project.get("reminders", [])))
        lines.extend(MemoryCoreService._render_section("Decision Log", project.get("decisions", [])))
        lines.extend(MemoryCoreService._render_section("Open Questions", project.get("open_questions", [])))
        lines.extend(MemoryCoreService._render_section("Conversation Memory", project.get("conversation_memory", [])))
        lines.extend(MemoryCoreService._render_section("Recent Changes", project.get("recent_changes", [])))
        lines.extend(MemoryCoreService._render_section("Observations", project.get("observations", [])))
        lines.extend(MemoryCoreService._render_section("Library Items", project.get("library_items", [])))
        lines.extend(MemoryCoreService._render_section("Skills & Behaviors", project.get("skills", [])))
        lines.extend(MemoryCoreService._render_section("Stack", project.get("stack", [])))
        lines.extend(MemoryCoreService._render_section("Important Files", project.get("important_files", []), code=True))
        lines.extend(MemoryCoreService._render_section("Useful Commands", project.get("commands", []), code=True))
        lines.extend(MemoryCoreService._render_section("Project Structure", project.get("structure", []), code=True))
        lines.extend(MemoryCoreService._render_section("Project Preferences", project.get("preferences", [])))
        lines.extend(MemoryCoreService._render_section("Project Notes", project.get("notes", [])))
        lines.extend(MemoryCoreService._render_activity_section(project.get("activity_log", [])))

        if profile:
            lines.extend(["", "## Identity Core", ""])
            if profile.get("display_name"):
                lines.append(f"- Name: {profile['display_name']}")
            if profile.get("about"):
                lines.append(f"- About: {profile['about']}")
            lines.extend(MemoryCoreService._render_section("General Preferences", profile.get("preferences", [])))
            lines.extend(MemoryCoreService._render_section("Coding Preferences", profile.get("coding_preferences", [])))
            lines.extend(MemoryCoreService._render_section("Workflow Preferences", profile.get("workflow_preferences", [])))
            lines.extend(MemoryCoreService._render_section("Identity Notes", profile.get("identity_notes", [])))
            lines.extend(MemoryCoreService._render_section("Relationship Memory", profile.get("relationship_notes", [])))
            lines.extend(MemoryCoreService._render_section("Standing Instructions", profile.get("standing_instructions", [])))
            lines.extend(MemoryCoreService._render_section("Persistent Notes", profile.get("notes", [])))

        lines.extend(
            [
                "",
                "## How To Use This",
                "",
                "- Use this file as standing context for new Codex or Claude Code sessions.",
                "- Treat the session briefing, reminders, decisions, and open questions as the fastest orientation layer.",
                "- Archive projects instead of deleting them when you want the memory to stay searchable but out of the hot path.",
                "- Keep it concise and update it when the project structure or preferences change.",
                "- The server copy is the source of truth; regenerate this file whenever you pull the latest memory.",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def render_master_memory(profile: dict | None, project: dict | None) -> str:
        lines = [
            "# Master Memory",
            "",
            "## Loader",
            "",
            "- This file is a portable memory entrypoint for AI sessions.",
            "- Load Identity Core, Relationship Memory, and Current Session before continuing work.",
        ]

        if profile:
            lines.extend(
                [
                    "",
                    "## Identity Core",
                    "",
                    f"- Name: {profile.get('display_name') or 'Unknown'}",
                ]
            )
            if profile.get("about"):
                lines.append(f"- About: {profile['about']}")
            lines.extend(MemoryCoreService._render_section("Preferences", profile.get("preferences", [])))
            lines.extend(MemoryCoreService._render_section("Coding Preferences", profile.get("coding_preferences", [])))
            lines.extend(MemoryCoreService._render_section("Workflow Preferences", profile.get("workflow_preferences", [])))
            lines.extend(MemoryCoreService._render_section("Identity Notes", profile.get("identity_notes", [])))
            lines.extend(MemoryCoreService._render_section("Relationship Memory", profile.get("relationship_notes", [])))
            lines.extend(MemoryCoreService._render_section("Standing Instructions", profile.get("standing_instructions", [])))

        if project:
            lines.extend(
                [
                    "",
                    "## Current Session",
                    "",
                    f"- Project: {project['title']}",
                    f"- Project key: {project['project_key']}",
                    f"- Status: {project.get('status', 'active')}",
                ]
            )
            if project.get("session_brief"):
                lines.append(f"- Briefing: {project['session_brief']}")
            if project.get("current_focus"):
                lines.append(f"- Current focus: {project['current_focus']}")
            if project.get("conversation_summary"):
                lines.append(f"- Conversation summary: {project['conversation_summary']}")
            lines.extend(MemoryCoreService._render_section("Goals", project.get("goals", [])))
            lines.extend(MemoryCoreService._render_section("Next Steps", project.get("next_steps", [])))
            lines.extend(MemoryCoreService._render_section("Reminders", project.get("reminders", [])))
            lines.extend(MemoryCoreService._render_section("Decision Log", project.get("decisions", [])))
            lines.extend(MemoryCoreService._render_section("Open Questions", project.get("open_questions", [])))
            lines.extend(MemoryCoreService._render_section("Conversation Memory", project.get("conversation_memory", [])))
            lines.extend(MemoryCoreService._render_section("Observations", project.get("observations", [])))
            lines.extend(MemoryCoreService._render_section("Library Items", project.get("library_items", [])))
            lines.extend(MemoryCoreService._render_section("Important Files", project.get("important_files", []), code=True))
            lines.extend(MemoryCoreService._render_section("Useful Commands", project.get("commands", []), code=True))
            lines.extend(MemoryCoreService._render_activity_section(project.get("activity_log", []), title="Project Timeline"))

        lines.extend(
            [
                "",
                "## Notes",
                "",
                "- This export is compatible with MemoryCore-style markdown workflows.",
                "- The server-backed Memory Core remains the source of truth.",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def build_session_briefing(db: Session, user_id: str, project_key: str | None = None) -> dict | None:
        project = None
        if project_key:
            project = MemoryCoreService.get_project(db, user_id=user_id, project_key=project_key)
        if project is None:
            projects = MemoryCoreService.list_projects(db, user_id=user_id)
            project = next((item for item in projects if item.get("status") != "archived"), projects[0] if projects else None)
        if project is None:
            return None

        lines = [f"## Session briefing for {project['title']}", ""]
        if project.get("session_brief"):
            lines.append(project["session_brief"])
            lines.append("")
        if project.get("current_focus"):
            lines.append(f"- Current focus: {project['current_focus']}")
        if project.get("conversation_summary"):
            lines.append(f"- Conversation memory: {project['conversation_summary']}")
        for item in project.get("conversation_memory", [])[:4]:
            lines.append(f"- Context: {item}")
        for item in project.get("next_steps", [])[:4]:
            lines.append(f"- Next: {item}")
        for item in project.get("reminders", [])[:3]:
            lines.append(f"- Reminder: {item}")
        for item in project.get("decisions", [])[:3]:
            lines.append(f"- Decision: {item}")
        if project.get("important_files"):
            lines.append(f"- Important files: {', '.join(project['important_files'][:4])}")
        if project.get("commands"):
            lines.append(f"- Useful commands: {', '.join(project['commands'][:3])}")

        return {
            "project_key": project["project_key"],
            "title": project["title"],
            "briefing": "\n".join(lines).strip(),
        }

    @staticmethod
    def import_master_memory(
        db: Session,
        user_id: str,
        content: str,
        project_key: str | None = None,
    ) -> dict:
        lines = [line.rstrip() for line in str(content or "").splitlines()]

        def extract_bullets(title: str) -> list[str]:
            target = title.lower()
            items: list[str] = []
            active = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("## "):
                    active = stripped[3:].strip().lower() == target
                    continue
                if active and stripped.startswith("- "):
                    items.append(stripped[2:].strip())
                elif active and stripped.startswith("## "):
                    break
            return items

        def find_prefixed(prefix: str) -> str | None:
            for line in lines:
                stripped = line.strip()
                if stripped.lower().startswith(prefix.lower()):
                    return stripped.split(":", 1)[1].strip() if ":" in stripped else stripped[len(prefix):].strip()
            return None

        title = find_prefixed("- Project") or find_prefixed("- Name") or project_key or "Imported project"
        normalized_project_key = MemoryCoreService.normalize_project_key(project_key or title)

        profile_payload = {
            "display_name": find_prefixed("- Name"),
            "about": find_prefixed("- About"),
            "preferences": extract_bullets("Preferences"),
            "coding_preferences": extract_bullets("Coding Preferences"),
            "workflow_preferences": extract_bullets("Workflow Preferences"),
            "identity_notes": extract_bullets("Identity Notes"),
            "relationship_notes": extract_bullets("Relationship Memory"),
            "standing_instructions": extract_bullets("Standing Instructions"),
        }
        project_payload = {
            "title": title,
            "summary": find_prefixed("- Briefing") or "",
            "current_focus": find_prefixed("- Current focus"),
            "conversation_summary": find_prefixed("- Conversation summary"),
            "goals": extract_bullets("Goals"),
            "next_steps": extract_bullets("Next Steps"),
            "reminders": extract_bullets("Reminders"),
            "decisions": extract_bullets("Decision Log"),
            "open_questions": extract_bullets("Open Questions"),
            "conversation_memory": extract_bullets("Conversation Memory"),
            "observations": extract_bullets("Observations"),
            "library_items": extract_bullets("Library Items"),
        }

        MemoryCoreService.upsert_profile(db, user_id=user_id, payload=profile_payload)
        project = MemoryCoreService.upsert_project(db, user_id=user_id, project_key=normalized_project_key, payload=project_payload)

        imported_fields = [
            key
            for key, value in {
                "profile": profile_payload,
                "project": project_payload,
            }.items()
            if any(bool(item) for item in (value.values() if isinstance(value, dict) else []))
        ]
        return {
            "project_key": project["project_key"],
            "title": project["title"],
            "imported_fields": imported_fields,
        }

    @staticmethod
    def build_assistant_context(db: Session, user_id: str, project_key: str | None = None) -> str:
        profile = MemoryCoreService.get_profile(db, user_id=user_id)
        project = MemoryCoreService.get_project(db, user_id=user_id, project_key=project_key) if project_key else None
        recent_projects = [] if project else MemoryCoreService.list_projects(db, user_id=user_id)[:2]

        sections: list[str] = []
        if profile:
            sections.append("User preferences:")
            for item in profile.get("preferences", [])[:6]:
                sections.append(f"- {item}")
            for item in profile.get("coding_preferences", [])[:6]:
                sections.append(f"- Coding: {item}")
            for item in profile.get("workflow_preferences", [])[:4]:
                sections.append(f"- Workflow: {item}")
            for item in profile.get("standing_instructions", [])[:5]:
                sections.append(f"- Standing instruction: {item}")
            for item in profile.get("relationship_notes", [])[:4]:
                sections.append(f"- Relationship memory: {item}")

        if project:
            sections.append(f"Current project: {project['title']} (`{project['project_key']}`)")
            if project.get("summary"):
                sections.append(f"- Summary: {project['summary']}")
            if project.get("session_brief"):
                sections.append(f"- Briefing: {project['session_brief']}")
            if project.get("current_focus"):
                sections.append(f"- Focus: {project['current_focus']}")
            if project.get("conversation_summary"):
                sections.append(f"- Conversation summary: {project['conversation_summary']}")
            for item in project.get("conversation_memory", [])[:5]:
                sections.append(f"- Conversation context: {item}")
            for item in project.get("stack", [])[:6]:
                sections.append(f"- Stack: {item}")
            for item in project.get("preferences", [])[:6]:
                sections.append(f"- Project pref: {item}")
            for item in project.get("next_steps", [])[:4]:
                sections.append(f"- Next: {item}")
            for item in project.get("reminders", [])[:4]:
                sections.append(f"- Reminder: {item}")
            for item in project.get("decisions", [])[:4]:
                sections.append(f"- Decision: {item}")
            for item in project.get("important_files", [])[:8]:
                sections.append(f"- Important file: {item}")
        elif recent_projects:
            sections.append("Recent project memory:")
            for item in recent_projects:
                label = item.get("title") or item.get("project_key")
                status = item.get("status", "active")
                sections.append(f"- {label} [{status}]")
                if item.get("current_focus"):
                    sections.append(f"  Focus: {item['current_focus']}")
                elif item.get("conversation_summary"):
                    sections.append(f"  Conversation: {item['conversation_summary']}")
                elif item.get("conversation_memory"):
                    sections.append(f"  Context: {item['conversation_memory'][0]}")
                elif item.get("session_brief"):
                    sections.append(f"  Briefing: {item['session_brief']}")
                elif item.get("summary"):
                    sections.append(f"  Summary: {item['summary']}")

        text = "\n".join(sections).strip()
        if len(text) > MemoryCoreService.CONTEXT_CHAR_LIMIT:
            return text[: MemoryCoreService.CONTEXT_CHAR_LIMIT].rstrip() + "..."
        return text

    @staticmethod
    def normalize_project_key(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
        return slug or "project"

    @staticmethod
    def _extract_conversation_memory(messages: list[Any]) -> dict[str, Any]:
        relevant_messages: list[dict[str, str]] = []
        for item in messages:
            content = str(getattr(item, "content", "") or "").strip()
            if not content:
                continue
            metadata = getattr(item, "metadata_json", {}) or {}
            provider = str(getattr(item, "provider", "") or "").strip().lower()
            if isinstance(metadata, dict) and metadata.get("memorycore_briefing"):
                continue
            if provider == "memorycore-briefing":
                continue
            role = MemoryCoreService._message_role(item)
            if role not in {"user", "assistant"}:
                continue
            relevant_messages.append({"role": role, "content": content})

        if not relevant_messages:
            return {
                "conversation_summary": "",
                "conversation_memory": [],
                "current_focus": None,
                "decisions": [],
                "next_steps": [],
                "open_questions": [],
                "recent_changes": [],
                "observations": [],
                "important_files": [],
                "commands": [],
            }

        recent_messages = relevant_messages[-24:]
        user_messages = [item["content"] for item in recent_messages if item["role"] == "user"]
        assistant_messages = [item["content"] for item in recent_messages if item["role"] == "assistant"]
        latest_user = user_messages[-1] if user_messages else ""
        latest_assistant = assistant_messages[-1] if assistant_messages else ""

        current_focus = MemoryCoreService._summarize_focus_from_text(latest_user)
        latest_outcome = MemoryCoreService._summarize_outcome_from_text(latest_assistant)
        summary_parts: list[str] = []
        if current_focus:
            summary_parts.append(f"Current objective: {current_focus}")
        if latest_outcome:
            summary_parts.append(f"Latest progress: {latest_outcome}")
        if not summary_parts and latest_user:
            summary_parts.append(MemoryCoreService._shorten_text(MemoryCoreService._clean_sentence(latest_user), 220))
        conversation_summary = " ".join(part for part in summary_parts if part).strip()

        conversation_memory: list[str] = []
        for content in user_messages[-3:]:
            focus = MemoryCoreService._summarize_focus_from_text(content)
            bullet = focus or MemoryCoreService._shorten_text(MemoryCoreService._clean_sentence(content), 170)
            if bullet:
                conversation_memory.append(f"User asked: {bullet}")
        for content in assistant_messages[-2:]:
            outcome = MemoryCoreService._summarize_outcome_from_text(content)
            bullet = outcome or MemoryCoreService._shorten_text(MemoryCoreService._clean_sentence(content), 170)
            if bullet:
                conversation_memory.append(f"Assistant concluded: {bullet}")

        decisions: list[str] = []
        next_steps: list[str] = []
        open_questions: list[str] = []
        recent_changes: list[str] = []
        observations: list[str] = []
        important_files: list[str] = []
        commands: list[str] = []

        for item in recent_messages:
            role = item["role"]
            content = item["content"]
            if role == "assistant":
                important_files.extend(MemoryCoreService._extract_file_references(content))
                commands.extend(MemoryCoreService._extract_command_lines(content))

            for line in MemoryCoreService._iter_message_lines(content):
                if role == "user":
                    open_questions.extend(MemoryCoreService._extract_questions(line))
                if role != "assistant":
                    continue
                if MemoryCoreService._looks_like_decision_line(line):
                    decisions.append(line)
                if MemoryCoreService._looks_like_next_step(line):
                    next_steps.append(line)
                if MemoryCoreService._looks_like_recent_change(line):
                    recent_changes.append(line)
                if MemoryCoreService._looks_like_observation(line):
                    observations.append(line)

        return {
            "conversation_summary": MemoryCoreService._shorten_text(conversation_summary, 360),
            "conversation_memory": MemoryCoreService._dedupe_preserve_order(conversation_memory, limit=8),
            "current_focus": current_focus,
            "decisions": MemoryCoreService._dedupe_preserve_order(decisions, limit=8),
            "next_steps": MemoryCoreService._dedupe_preserve_order(next_steps, limit=8),
            "open_questions": MemoryCoreService._dedupe_preserve_order(open_questions, limit=8),
            "recent_changes": MemoryCoreService._dedupe_preserve_order(recent_changes, limit=8),
            "observations": MemoryCoreService._dedupe_preserve_order(observations, limit=8),
            "important_files": MemoryCoreService._dedupe_preserve_order(important_files, limit=10),
            "commands": MemoryCoreService._dedupe_preserve_order(commands, limit=8),
        }

    @staticmethod
    def _message_role(message: Any) -> str:
        role = getattr(message, "role", "")
        if hasattr(role, "value"):
            return str(role.value).strip().lower()
        return str(role).strip().lower()

    @staticmethod
    def _iter_message_lines(content: str) -> list[str]:
        plain = re.sub(r"```[\s\S]*?```", "\n", str(content or ""))
        plain = re.sub(r"`([^`\n]+)`", r"\1", plain)
        plain = re.sub(r"\[[^\]]+\]\(([^)]+)\)", r"\1", plain)
        candidates: list[str] = []
        for raw_line in re.split(r"\n+", plain):
            stripped_line = raw_line.strip()
            if not stripped_line:
                continue
            segments = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", stripped_line)
            for segment in segments:
                cleaned = MemoryCoreService._clean_sentence(segment)
                if cleaned:
                    candidates.append(cleaned)
        return candidates

    @staticmethod
    def _clean_sentence(value: str) -> str:
        text = str(value or "").strip()
        text = re.sub(r"^\s*(?:[-*]|\d+\.)\s*", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip(" -")

    @staticmethod
    def _shorten_text(value: str, limit: int = 180) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        shortened = text[: max(limit - 3, 1)].rstrip(" ,.;:")
        return f"{shortened}..."

    @staticmethod
    def _summarize_focus_from_text(text: str) -> str | None:
        cleaned = MemoryCoreService._clean_sentence(text)
        if not cleaned:
            return None
        lowered = cleaned.lower()
        prefixes = (
            "can you ",
            "could you ",
            "please ",
            "i want you to ",
            "i need you to ",
            "help me ",
            "now ",
        )
        for prefix in prefixes:
            if lowered.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                lowered = cleaned.lower()
        cleaned = re.sub(r"\b(?:for me|please)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        if not cleaned:
            return None
        if len(cleaned.split()) > 18:
            cleaned = " ".join(cleaned.split()[:18]).strip()
        return MemoryCoreService._shorten_text(cleaned[:1].upper() + cleaned[1:], 170)

    @staticmethod
    def _summarize_outcome_from_text(text: str) -> str | None:
        lines = MemoryCoreService._iter_message_lines(text)
        if not lines:
            return None
        preferred = []
        for line in lines:
            lowered = line.lower()
            if any(
                token in lowered
                for token in (
                    "fixed",
                    "updated",
                    "added",
                    "wired",
                    "patched",
                    "rebuilt",
                    "implemented",
                    "now",
                    "verified",
                    "deployed",
                )
            ):
                preferred.append(line)
        chosen = preferred[0] if preferred else lines[0]
        return MemoryCoreService._shorten_text(chosen, 190)

    @staticmethod
    def _looks_like_decision_line(line: str) -> bool:
        lowered = line.lower()
        if "?" in lowered:
            return False
        return bool(
            re.search(
                r"\b(use|prefer|keep|set|switch|default|route|treat|choose|standardize|store|save)\b",
                lowered,
            )
        )

    @staticmethod
    def _looks_like_next_step(line: str) -> bool:
        lowered = line.lower()
        if "?" in lowered:
            return False
        return bool(
            re.match(
                r"^(run|restart|deploy|rebuild|pull|update|replace|verify|open|try|use|set|download|install|hard refresh|refresh)\b",
                lowered,
            )
        )

    @staticmethod
    def _looks_like_recent_change(line: str) -> bool:
        lowered = line.lower()
        return bool(
            re.search(
                r"\b(i fixed|i updated|i changed|i added|i wired|i patched|i rebuilt|i upgraded|i implemented|the app is now|is now|now)\b",
                lowered,
            )
        )

    @staticmethod
    def _looks_like_observation(line: str) -> bool:
        lowered = line.lower()
        return any(
            token in lowered
            for token in (
                "important",
                "note:",
                "limit",
                "warning",
                "currently",
                "right now",
                "blocked",
                "offline",
                "online",
                "issue",
                "problem",
            )
        )

    @staticmethod
    def _extract_questions(line: str) -> list[str]:
        cleaned = MemoryCoreService._clean_sentence(line)
        if not cleaned:
            return []
        lowered = cleaned.lower()
        if "?" in cleaned or re.match(r"^(can|could|should|would|what|why|how|when|where|is|are|do|does)\b", lowered):
            return [MemoryCoreService._shorten_text(cleaned.rstrip("?") + "?", 170)]
        return []

    @staticmethod
    def _extract_file_references(text: str) -> list[str]:
        candidates: list[str] = []
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", str(text or "")):
            stripped = str(target).strip()
            if re.search(r"\.[a-z0-9]{1,8}(?::\d+)?(?:[#:].*)?$", stripped, flags=re.IGNORECASE):
                candidates.append(stripped)
        for target in re.findall(r"`([^`\n]+)`", str(text or "")):
            stripped = str(target).strip()
            if any(sep in stripped for sep in ("\\", "/")) and re.search(r"\.[a-z0-9]{1,8}", stripped, flags=re.IGNORECASE):
                candidates.append(stripped)
        return candidates

    @staticmethod
    def _extract_command_lines(text: str) -> list[str]:
        commands: list[str] = []
        raw_text = str(text or "")
        for block in re.findall(r"```(?:[\w.+-]+)?\n([\s\S]*?)```", raw_text):
            for line in block.splitlines():
                candidate = line.strip()
                if MemoryCoreService._looks_like_command(candidate):
                    commands.append(candidate)
        for inline in re.findall(r"`([^`\n]+)`", raw_text):
            candidate = inline.strip()
            if MemoryCoreService._looks_like_command(candidate):
                commands.append(candidate)
        return commands

    @staticmethod
    def _looks_like_command(text: str) -> bool:
        candidate = str(text or "").strip()
        if not candidate or len(candidate) > 180:
            return False
        return bool(
            re.match(
                r"^(docker(?:-compose)?|git|python|py|pip|npm|pnpm|yarn|curl|uv|ollama|powershell|pwsh|\.\\|/|cd\s+)",
                candidate,
                flags=re.IGNORECASE,
            )
        )

    @staticmethod
    def _dedupe_preserve_order(items: list[str], *, limit: int = 8) -> list[str]:
        results: list[str] = []
        seen: set[str] = set()
        for item in items:
            cleaned = MemoryCoreService._shorten_text(MemoryCoreService._clean_sentence(item), 220)
            lowered = cleaned.lower()
            if not cleaned or lowered in seen:
                continue
            seen.add(lowered)
            results.append(cleaned)
            if len(results) >= limit:
                break
        return results

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
        last_opened_at = MemoryCoreService._parse_datetime(payload.get("last_opened_at"))
        return {
            "user_id": user_id,
            **payload,
            "next_steps_count": len(payload.get("next_steps", [])),
            "reminders_count": len(payload.get("reminders", [])),
            "decisions_count": len(payload.get("decisions", [])),
            "library_items_count": len(payload.get("library_items", [])),
            "open_questions_count": len(payload.get("open_questions", [])),
            "last_opened_at": last_opened_at,
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
            "identity_notes": MemoryCoreService._clean_list(payload.get("identity_notes")),
            "relationship_notes": MemoryCoreService._clean_list(payload.get("relationship_notes")),
            "standing_instructions": MemoryCoreService._clean_list(payload.get("standing_instructions")),
            "notes": MemoryCoreService._clean_list(payload.get("notes")),
            "tags": MemoryCoreService._clean_list(payload.get("tags")),
            "schema_version": 2,
        }

    @staticmethod
    def _normalize_project_payload(project_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        title = MemoryCoreService._clean_text(payload.get("title")) or project_key.replace("-", " ").title()
        summary = MemoryCoreService._clean_text(payload.get("summary")) or ""
        stack = MemoryCoreService._clean_list(payload.get("stack"))
        goals = MemoryCoreService._clean_list(payload.get("goals"))
        next_steps = MemoryCoreService._clean_list(payload.get("next_steps"))
        reminders = MemoryCoreService._clean_list(payload.get("reminders"))
        decisions = MemoryCoreService._clean_list(payload.get("decisions"))
        observations = MemoryCoreService._clean_list(payload.get("observations"))
        library_items = MemoryCoreService._clean_list(payload.get("library_items"))
        open_questions = MemoryCoreService._clean_list(payload.get("open_questions"))
        recent_changes = MemoryCoreService._clean_list(payload.get("recent_changes"))
        skills = MemoryCoreService._clean_list(payload.get("skills"))
        conversation_summary = MemoryCoreService._clean_text(payload.get("conversation_summary")) or ""
        conversation_memory = MemoryCoreService._clean_list(payload.get("conversation_memory"))
        linked_sessions = MemoryCoreService._clean_list(payload.get("linked_sessions"))
        activity_log = MemoryCoreService._normalize_activity_log(payload.get("activity_log"))
        session_brief = MemoryCoreService._clean_text(payload.get("session_brief")) or MemoryCoreService._auto_session_brief(
            title=title,
            summary=conversation_summary or summary,
            stack=stack,
            current_focus=MemoryCoreService._clean_text(payload.get("current_focus")),
            next_steps=next_steps,
        )
        return {
            "project_key": MemoryCoreService.normalize_project_key(project_key),
            "title": title,
            "summary": summary,
            "status": MemoryCoreService._normalize_status(payload.get("status")),
            "root_hint": MemoryCoreService._clean_text(payload.get("root_hint")),
            "repo_origin": MemoryCoreService._clean_text(payload.get("repo_origin")),
            "current_focus": MemoryCoreService._clean_text(payload.get("current_focus")),
            "session_brief": session_brief,
            "stack": stack,
            "goals": goals,
            "next_steps": next_steps,
            "reminders": reminders,
            "decisions": decisions,
            "observations": observations,
            "library_items": library_items,
            "open_questions": open_questions,
            "conversation_summary": conversation_summary,
            "conversation_memory": conversation_memory,
            "recent_changes": recent_changes,
            "skills": skills,
            "linked_sessions": linked_sessions,
            "activity_log": activity_log,
            "important_files": MemoryCoreService._clean_list(payload.get("important_files")),
            "commands": MemoryCoreService._clean_list(payload.get("commands")),
            "structure": MemoryCoreService._clean_list(payload.get("structure")),
            "preferences": MemoryCoreService._clean_list(payload.get("preferences")),
            "notes": MemoryCoreService._clean_list(payload.get("notes")),
            "tags": MemoryCoreService._clean_list(payload.get("tags")),
            "last_opened_at": MemoryCoreService._clean_text(payload.get("last_opened_at")),
            "open_count": MemoryCoreService._clean_int(payload.get("open_count"), minimum=0),
            "schema_version": 2,
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
    def _clean_int(value: Any, *, minimum: int = 0) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return minimum
        return max(minimum, parsed)

    @staticmethod
    def _normalize_activity_log(value: Any) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        results: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind", "")).strip().lower() or "note"
            detail = str(item.get("detail", "")).strip()
            at = str(item.get("at", "")).strip()
            if not detail:
                continue
            results.append({"kind": kind, "detail": detail, "at": at})
        return results[: MemoryCoreService.ACTIVITY_LOG_LIMIT]

    @staticmethod
    def _normalize_status(value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in MemoryCoreService.PROJECT_STATUSES:
            return text
        return "active"

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _project_sort_key(project: dict[str, Any]) -> tuple[int, float, float]:
        status_rank = 0 if project.get("status") == "active" else 1
        last_opened = project.get("last_opened_at")
        updated_at = project.get("updated_at")
        last_opened_ts = last_opened.timestamp() if isinstance(last_opened, datetime) else 0.0
        updated_ts = updated_at.timestamp() if isinstance(updated_at, datetime) else 0.0
        return (status_rank, -max(last_opened_ts, updated_ts), -updated_ts)

    @staticmethod
    def _append_activity_event(current_log: Any, *, kind: str, detail: str) -> list[dict[str, str]]:
        normalized = MemoryCoreService._normalize_activity_log(current_log)
        event = {
            "kind": kind,
            "detail": detail,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        return [event, *normalized][: MemoryCoreService.ACTIVITY_LOG_LIMIT]

    @staticmethod
    def _append_project_activity(
        db: Session,
        *,
        user_id: str,
        project_key: str,
        kind: str,
        detail: str,
    ) -> dict | None:
        record = db.scalar(
            select(AppSetting).where(AppSetting.key == MemoryCoreService._project_key(user_id, project_key))
        )
        if record is None:
            return None
        payload = dict(record.value_json or {})
        payload["activity_log"] = MemoryCoreService._append_activity_event(payload.get("activity_log"), kind=kind, detail=detail)
        record.value_json = MemoryCoreService._normalize_project_payload(
            str(payload.get("project_key") or project_key),
            payload,
        )
        db.commit()
        db.refresh(record)
        return MemoryCoreService._serialize_project(user_id, record)

    @staticmethod
    def _merge_unique_lists(existing: Any, additions: Any) -> list[str]:
        items = MemoryCoreService._clean_list(existing)
        seen = {item.lower() for item in items}
        for item in MemoryCoreService._clean_list(additions):
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            items.append(item)
        return items[:80]

    @staticmethod
    def _summarize_project_save(*, current: dict[str, Any], merged: dict[str, Any], created: bool) -> str:
        if created:
            return "Created project memory."
        changes: list[str] = []
        if current.get("current_focus") != merged.get("current_focus") and merged.get("current_focus"):
            changes.append(f"Updated focus to {merged['current_focus']}.")
        if current.get("status") != merged.get("status"):
            changes.append(f"Status set to {merged['status']}.")
        if not changes:
            changes.append("Saved project memory snapshot.")
        return " ".join(changes)

    @staticmethod
    def _render_activity_section(activity_log: list[dict[str, str]], *, title: str = "Activity Timeline") -> list[str]:
        if not activity_log:
            return []
        lines = ["", f"## {title}", ""]
        for item in activity_log:
            detail = str(item.get("detail", "")).strip()
            at = str(item.get("at", "")).strip()
            if at:
                lines.append(f"- [{at}] {detail}")
            elif detail:
                lines.append(f"- {detail}")
        return lines

    @staticmethod
    def _auto_session_brief(
        *,
        title: str,
        summary: str,
        stack: list[str],
        current_focus: str | None,
        next_steps: list[str],
    ) -> str:
        parts: list[str] = []
        if summary:
            parts.append(summary.rstrip("."))
        else:
            parts.append(f"{title} is an actively tracked project")
        if current_focus:
            parts.append(f"Current focus: {current_focus.rstrip('.')}")
        elif next_steps:
            parts.append(f"Immediate next step: {next_steps[0].rstrip('.')}")
        if stack:
            parts.append(f"Main stack: {', '.join(stack[:4])}")
        return ". ".join(part for part in parts if part).strip().rstrip(".") + "."

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
    def _session_link_prefix(user_id: str) -> str:
        return f"{MemoryCoreService.SESSION_LINK_PREFIX}:{MemoryCoreService._user_token(user_id)}:"

    @staticmethod
    def _session_link_key(user_id: str, session_id: str) -> str:
        return f"{MemoryCoreService._session_link_prefix(user_id)}{MemoryCoreService._project_token(session_id)}"

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
