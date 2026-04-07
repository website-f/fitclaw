from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.task import TaskContinueRequest, TaskCreateRequest, TaskResponse
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreateRequest, db: Session = Depends(get_db)):
    return TaskService.create_task(
        db=db,
        title=payload.title,
        description=payload.description,
        assigned_agent_name=payload.assigned_agent_name,
        source=payload.source,
        command_type=payload.command_type,
        created_by_user_id=payload.created_by_user_id,
        user_session_id=payload.user_session_id,
        metadata_json=payload.metadata_json,
    )


@router.get("", response_model=list[TaskResponse])
def list_tasks(
    user_id: str | None = Query(default=None, max_length=120),
    session_id: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return TaskService.list_tasks(db, created_by_user_id=user_id, user_session_id=session_id, limit=limit)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = TaskService.get_task_by_task_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task


@router.post("/{task_id}/continue", response_model=TaskResponse)
def continue_task(task_id: str, payload: TaskContinueRequest, db: Session = Depends(get_db)):
    task = TaskService.continue_task(db, task_id=task_id, note=payload.note, reset_to_pending=payload.reset_to_pending)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task

