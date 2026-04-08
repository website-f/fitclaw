from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.agent import AgentHeartbeatRequest, AgentModelPreferences, AgentModelPreferencesUpdate, AgentRegisterRequest, AgentResponse
from app.services.agent_service import AgentService

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.post("/register", response_model=AgentResponse)
def register_agent(payload: AgentRegisterRequest, db: Session = Depends(get_db)):
    agent = AgentService.register_agent(
        db=db,
        name=payload.name,
        capabilities_json=payload.capabilities_json,
        metadata_json=payload.metadata_json,
    )
    return AgentService.serialize_agent(agent)


@router.post("/heartbeat", response_model=AgentResponse)
def heartbeat_agent(payload: AgentHeartbeatRequest, db: Session = Depends(get_db)):
    agent = AgentService.heartbeat(
        db=db,
        name=payload.name,
        status=payload.status,
        current_task_id=payload.current_task_id,
        metadata_json=payload.metadata_json,
    )
    return AgentService.serialize_agent(agent)


@router.get("", response_model=list[AgentResponse])
def list_agents(db: Session = Depends(get_db)):
    return [AgentService.serialize_agent(agent) for agent in AgentService.list_agents(db)]


@router.get("/{name}", response_model=AgentResponse)
def get_agent(name: str, db: Session = Depends(get_db)):
    agent = AgentService.get_agent(db, name)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    return AgentService.serialize_agent(agent)


@router.get("/{name}/models", response_model=AgentModelPreferences)
def get_agent_model_preferences(name: str, db: Session = Depends(get_db)):
    agent = AgentService.get_agent(db, name)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    return AgentService.serialize_agent(agent).model_preferences


@router.patch("/{name}/models", response_model=AgentResponse)
def update_agent_model_preferences(name: str, payload: AgentModelPreferencesUpdate, db: Session = Depends(get_db)):
    agent = AgentService.update_model_preferences(
        db=db,
        name=name,
        preferred_text=payload.preferred_text.model_dump() if payload.preferred_text else None,
        preferred_vision=payload.preferred_vision.model_dump() if payload.preferred_vision else None,
        allowed_models=[item.model_dump() for item in payload.allowed_models],
    )
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    return AgentService.serialize_agent(agent)
