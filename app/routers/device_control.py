from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.agent import AgentResponse
from app.schemas.device_control import (
    DeviceCommandCreateRequest,
    DeviceCommandResponse,
    StorageDeleteRequest,
    StorageInspectRequest,
)
from app.services.agent_service import AgentService
from app.services.control_workflow_service import ControlWorkflowService
from app.services.device_control_service import DeviceControlService

router = APIRouter(tags=["device-control"])


@router.get("/control", include_in_schema=False)
def control_panel():
    file_path = Path(__file__).resolve().parents[1] / "ui" / "control_panel.html"
    return FileResponse(file_path)


@router.post("/api/v1/control/commands", response_model=DeviceCommandResponse, status_code=status.HTTP_201_CREATED)
def create_device_command(payload: DeviceCommandCreateRequest, db: Session = Depends(get_db)):
    return DeviceControlService.create_command(
        db=db,
        agent_name=payload.agent_name,
        command_type=payload.command_type,
        payload_json=payload.payload_json,
        source=payload.source,
        created_by_user_id=payload.created_by_user_id,
    )


@router.get("/api/v1/control/agents", response_model=list[AgentResponse])
def list_control_agents(db: Session = Depends(get_db)):
    return [AgentService.serialize_agent(agent) for agent in AgentService.list_agents(db)]


@router.get("/api/v1/control/commands", response_model=list[DeviceCommandResponse])
def list_device_commands(
    agent_name: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return DeviceControlService.list_commands(db, agent_name=agent_name, limit=limit)


@router.get("/api/v1/control/commands/{command_id}", response_model=DeviceCommandResponse)
def get_device_command(command_id: str, db: Session = Depends(get_db)):
    command = DeviceControlService.get_command(db, command_id)
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device command not found.")
    return command


@router.get("/api/v1/control/commands/{command_id}/artifact", include_in_schema=False)
def get_device_command_artifact(command_id: str, db: Session = Depends(get_db)):
    command = DeviceControlService.get_command(db, command_id)
    if command is None or not command.artifact_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")

    file_path = Path(command.artifact_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact file is missing.")
    return FileResponse(file_path)


@router.post("/api/v1/control/storage/inspect")
def inspect_storage(payload: StorageInspectRequest, db: Session = Depends(get_db)):
    try:
        return ControlWorkflowService.inspect_storage(
            db=db,
            agent_name=payload.agent_name,
            path=payload.path,
            top_n=payload.top_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/api/v1/control/storage/delete")
def delete_storage_path(payload: StorageDeleteRequest, db: Session = Depends(get_db)):
    try:
        return ControlWorkflowService.delete_path(
            db=db,
            agent_name=payload.agent_name,
            path=payload.path,
            use_trash=payload.use_trash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
