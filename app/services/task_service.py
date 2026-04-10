from datetime import datetime, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.agent import AgentStatus
from app.models.base import utcnow
from app.models.task import Task, TaskStatus
from app.services.agent_service import AgentService


class TaskService:
    @staticmethod
    def _parse_not_before(task: Task) -> datetime | None:
        raw = str((task.metadata_json or {}).get("not_before_at", "")).strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _is_ready_to_run(task: Task, now: datetime) -> bool:
        not_before = TaskService._parse_not_before(task)
        if not_before is None:
            return True
        return not_before <= now

    @staticmethod
    def build_title_from_text(text: str) -> str:
        cleaned = " ".join(text.strip().split())
        return cleaned[:80] if len(cleaned) > 80 else cleaned

    @staticmethod
    def create_task(
        db: Session,
        title: str,
        description: str,
        assigned_agent_name: str | None = None,
        source: str = "api",
        command_type: str | None = None,
        created_by_user_id: str | None = None,
        user_session_id: str | None = None,
        metadata_json: dict | None = None,
    ) -> Task:
        cleaned_description = description.strip()
        cleaned_title = title.strip() or TaskService.build_title_from_text(cleaned_description) or "Untitled task"
        task = Task(
            title=cleaned_title,
            description=cleaned_description,
            assigned_agent_name=assigned_agent_name,
            source=source,
            command_type=command_type,
            created_by_user_id=created_by_user_id,
            user_session_id=user_session_id,
            metadata_json=metadata_json or {},
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def get_task_by_task_id(db: Session, task_id: str) -> Task | None:
        return db.scalar(select(Task).where(Task.task_id == task_id))

    @staticmethod
    def list_tasks(
        db: Session,
        created_by_user_id: str | None = None,
        user_session_id: str | None = None,
        limit: int = 20,
    ) -> list[Task]:
        stmt = select(Task)
        if created_by_user_id:
            stmt = stmt.where(Task.created_by_user_id == created_by_user_id)
        if user_session_id:
            stmt = stmt.where(Task.user_session_id == user_session_id)
        stmt = stmt.order_by(Task.created_at.desc()).limit(limit)
        return list(db.scalars(stmt).all())

    @staticmethod
    def continue_task(db: Session, task_id: str, note: str, reset_to_pending: bool = True) -> Task | None:
        task = TaskService.get_task_by_task_id(db, task_id)
        if task is None:
            return None

        continuation_block = f"\n\n[Continuation {utcnow().isoformat()}]\n{note.strip()}"
        task.description = f"{task.description.rstrip()}{continuation_block}"
        task.metadata_json = {**task.metadata_json, "last_continuation_note": note.strip()}

        if reset_to_pending and task.status != TaskStatus.in_progress:
            task.status = TaskStatus.pending
            task.started_at = None
            task.completed_at = None
            task.result_text = None
            task.error_text = None

        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def claim_next_task(db: Session, agent_name: str, allow_unassigned: bool = True) -> Task | None:
        filters = [Task.status == TaskStatus.pending]
        if allow_unassigned:
            filters.append(or_(Task.assigned_agent_name == agent_name, Task.assigned_agent_name.is_(None)))
        else:
            filters.append(Task.assigned_agent_name == agent_name)

        candidates = list(db.scalars(select(Task).where(*filters).order_by(Task.created_at.asc()).limit(25)).all())
        now = utcnow()

        for candidate in candidates:
            if not TaskService._is_ready_to_run(candidate, now):
                continue
            result = db.execute(
                update(Task)
                .where(Task.id == candidate.id)
                .where(Task.status == TaskStatus.pending)
                .values(
                    status=TaskStatus.in_progress,
                    assigned_agent_name=agent_name,
                    started_at=now,
                    updated_at=now,
                )
            )

            if result.rowcount:
                db.commit()
                AgentService.mark_task_state(db, agent_name, AgentStatus.busy, current_task_id=candidate.task_id)
                return TaskService.get_task_by_task_id(db, candidate.task_id)

        db.rollback()
        return None

    @staticmethod
    def update_task_result(
        db: Session,
        task_id: str,
        agent_name: str,
        status: TaskStatus,
        result_text: str | None = None,
        error_text: str | None = None,
        metadata_json: dict | None = None,
    ) -> Task | None:
        task = TaskService.get_task_by_task_id(db, task_id)
        if task is None:
            return None

        task.assigned_agent_name = task.assigned_agent_name or agent_name
        task.status = status
        task.result_text = result_text
        task.error_text = error_text
        task.metadata_json = {**task.metadata_json, **(metadata_json or {})}

        if status in {TaskStatus.completed, TaskStatus.failed}:
            task.completed_at = utcnow()
            AgentService.mark_task_state(db, agent_name, AgentStatus.online, current_task_id=None)
        else:
            task.completed_at = None
            if task.started_at is None:
                task.started_at = utcnow()
            AgentService.mark_task_state(db, agent_name, AgentStatus.busy, current_task_id=task.task_id)

        db.commit()
        db.refresh(task)
        return task
