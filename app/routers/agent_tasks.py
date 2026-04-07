from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.task import TaskClaimRequest, TaskResponse, TaskResultRequest
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/v1/agent-tasks", tags=["agent-tasks"])


@router.post("/claim", response_model=TaskResponse | None)
def claim_task(payload: TaskClaimRequest, db: Session = Depends(get_db)):
    task = TaskService.claim_next_task(
        db=db,
        agent_name=payload.agent_name,
        allow_unassigned=payload.allow_unassigned,
    )
    return task


@router.post("/{task_id}/result", response_model=TaskResponse)
def post_task_result(task_id: str, payload: TaskResultRequest, db: Session = Depends(get_db)):
    task = TaskService.update_task_result(
        db=db,
        task_id=task_id,
        agent_name=payload.agent_name,
        status=payload.status,
        result_text=payload.result_text,
        error_text=payload.error_text,
        metadata_json=payload.metadata_json,
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    return task

