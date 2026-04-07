import re

from sqlalchemy.orm import Session

from app.services.command_result import CommandResult
from app.services.task_service import TaskService


class TaskCommandService:
    START_PATTERN = re.compile(r"^start task\b", re.IGNORECASE)
    STATUS_PATTERN = re.compile(r"^(check status|status)\b", re.IGNORECASE)
    CONTINUE_PATTERN = re.compile(r"^continue task\b", re.IGNORECASE)

    @classmethod
    def try_handle(cls, db: Session, user_id: str, session_id: str, text: str) -> CommandResult | None:
        normalized = text.strip()

        if cls.START_PATTERN.match(normalized):
            return cls._handle_start(db, user_id, session_id, normalized)
        if cls.STATUS_PATTERN.match(normalized):
            return cls._handle_status(db, user_id, session_id, normalized)
        if cls.CONTINUE_PATTERN.match(normalized):
            return cls._handle_continue(db, normalized)

        return None

    @classmethod
    def _handle_start(cls, db: Session, user_id: str, session_id: str, text: str) -> CommandResult:
        payload = cls.START_PATTERN.sub("", text, count=1).strip()
        if not payload:
            return CommandResult(
                reply=(
                    "Use `start task <description>` or `start task office-pc: <description>` "
                    "to queue work for an agent."
                ),
                handled_as_task_command=True,
            )

        agent_name, description = cls._extract_agent_and_description(payload)
        if not description:
            return CommandResult(
                reply=(
                    "I need a task description. Use `start task <description>` or "
                    "`start task office-pc: <description>`."
                ),
                handled_as_task_command=True,
            )
        task = TaskService.create_task(
            db=db,
            title=TaskService.build_title_from_text(description),
            description=description,
            assigned_agent_name=agent_name,
            source="telegram",
            command_type="start_task",
            created_by_user_id=user_id,
            user_session_id=session_id,
            metadata_json={"origin_text": text},
        )

        target = agent_name or "any available agent"
        return CommandResult(
            reply=f"Task `{task.task_id}` created for {target} with status `{task.status.value}`.\n{task.title}",
            handled_as_task_command=True,
        )

    @classmethod
    def _handle_status(cls, db: Session, user_id: str, session_id: str, text: str) -> CommandResult:
        payload = cls.STATUS_PATTERN.sub("", text, count=1).strip()

        if payload:
            task = TaskService.get_task_by_task_id(db, payload)
            if task is None:
                return CommandResult(reply=f"I couldn't find task `{payload}`.", handled_as_task_command=True)

            assigned = task.assigned_agent_name or "unassigned"
            result_line = f"\nResult: {task.result_text}" if task.result_text else ""
            error_line = f"\nError: {task.error_text}" if task.error_text else ""
            return CommandResult(
                reply=(
                    f"Task `{task.task_id}` is `{task.status.value}`.\n"
                    f"Agent: {assigned}\n"
                    f"Title: {task.title}{result_line}{error_line}"
                ),
                handled_as_task_command=True,
            )

        tasks = TaskService.list_tasks(db, created_by_user_id=user_id, user_session_id=session_id, limit=5)
        if not tasks:
            return CommandResult(reply="There are no tracked tasks yet for this session.", handled_as_task_command=True)

        lines = []
        for task in tasks:
            agent = task.assigned_agent_name or "unassigned"
            lines.append(f"- {task.task_id}: {task.status.value} ({agent}) {task.title}")
        return CommandResult(reply="Recent tasks:\n" + "\n".join(lines), handled_as_task_command=True)

    @classmethod
    def _handle_continue(cls, db: Session, text: str) -> CommandResult:
        payload = cls.CONTINUE_PATTERN.sub("", text, count=1).strip()
        parts = payload.split(maxsplit=1)
        if len(parts) < 2:
            return CommandResult(reply="Use `continue task <task_id> <additional instructions>`.", handled_as_task_command=True)

        task_id, note = parts
        task = TaskService.continue_task(db, task_id=task_id, note=note, reset_to_pending=True)
        if task is None:
            return CommandResult(reply=f"I couldn't find task `{task_id}`.", handled_as_task_command=True)

        status_text = task.status.value
        return CommandResult(reply=f"Task `{task.task_id}` was updated and is now `{status_text}`.", handled_as_task_command=True)

    @staticmethod
    def _extract_agent_and_description(payload: str) -> tuple[str | None, str]:
        patterns = (
            re.compile(r"^(?:for|on)\s+(?P<agent>[\w.-]+)\s+(?P<description>.+)$", re.IGNORECASE),
            re.compile(r"^@(?P<agent>[\w.-]+)\s+(?P<description>.+)$", re.IGNORECASE),
            re.compile(r"^(?P<agent>[\w.-]+)\s*[:|]\s*(?P<description>.+)$", re.IGNORECASE),
        )

        for pattern in patterns:
            match = pattern.match(payload)
            if match:
                return match.group("agent"), match.group("description").strip()

        return None, payload.strip()
