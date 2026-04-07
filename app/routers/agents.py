from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.agent import AgentHeartbeatRequest, AgentRegisterRequest, AgentResponse
from app.services.agent_service import AgentService

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.post("/register", response_model=AgentResponse)
def register_agent(payload: AgentRegisterRequest, db: Session = Depends(get_db)):
    return AgentService.register_agent(
        db=db,
        name=payload.name,
        capabilities_json=payload.capabilities_json,
        metadata_json=payload.metadata_json,
    )


@router.post("/heartbeat", response_model=AgentResponse)
def heartbeat_agent(payload: AgentHeartbeatRequest, db: Session = Depends(get_db)):
    return AgentService.heartbeat(
        db=db,
        name=payload.name,
        status=payload.status,
        current_task_id=payload.current_task_id,
        metadata_json=payload.metadata_json,
    )


@router.get("", response_model=list[AgentResponse])
def list_agents(db: Session = Depends(get_db)):
    return AgentService.list_agents(db)


@router.get("/{name}", response_model=AgentResponse)
def get_agent(name: str, db: Session = Depends(get_db)):
    agent = AgentService.get_agent(db, name)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    return agent

