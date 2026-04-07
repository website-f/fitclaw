from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.device_control import DeviceCommandResponse, DeviceCommandResultRequest
from app.services.device_control_service import DeviceControlService

router = APIRouter(prefix="/api/v1/agent-control", tags=["agent-control"])


@router.post("/claim/{agent_name}", response_model=DeviceCommandResponse | None)
def claim_agent_control_command(agent_name: str, db: Session = Depends(get_db)):
    return DeviceControlService.claim_next_command(db, agent_name=agent_name)


@router.post("/{command_id}/result", response_model=DeviceCommandResponse)
def submit_agent_control_result(command_id: str, payload: DeviceCommandResultRequest, db: Session = Depends(get_db)):
    command = DeviceControlService.complete_command(
        db=db,
        command_id=command_id,
        status=payload.status,
        result_json=payload.result_json,
        error_text=payload.error_text,
    )
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device command not found.")
    return command

