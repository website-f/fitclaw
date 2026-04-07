import json
from datetime import timedelta

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.agent import Agent, AgentStatus
from app.models.base import utcnow

settings = get_settings()
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


class AgentService:
    @staticmethod
    def _heartbeat_key(name: str) -> str:
        return f"agent:heartbeat:{name}"

    @staticmethod
    def register_agent(
        db: Session, name: str, capabilities_json: list[str] | None = None, metadata_json: dict | None = None
    ) -> Agent:
        agent = db.scalar(select(Agent).where(Agent.name == name))
        now = utcnow()

        if agent is None:
            agent = Agent(
                name=name,
                capabilities_json=capabilities_json or [],
                metadata_json=metadata_json or {},
                status=AgentStatus.online,
                last_heartbeat_at=now,
            )
            db.add(agent)
        else:
            agent.capabilities_json = capabilities_json or agent.capabilities_json
            agent.metadata_json = {**agent.metadata_json, **(metadata_json or {})}
            agent.status = AgentStatus.online
            agent.last_heartbeat_at = now

        db.commit()
        db.refresh(agent)
        AgentService._write_heartbeat(agent)
        return agent

    @staticmethod
    def heartbeat(
        db: Session, name: str, status: AgentStatus = AgentStatus.online, current_task_id: str | None = None, metadata_json: dict | None = None
    ) -> Agent:
        agent = db.scalar(select(Agent).where(Agent.name == name))
        now = utcnow()

        if agent is None:
            agent = Agent(
                name=name,
                status=status,
                current_task_id=current_task_id,
                metadata_json=metadata_json or {},
                capabilities_json=[],
                last_heartbeat_at=now,
            )
            db.add(agent)
        else:
            agent.status = status
            agent.current_task_id = current_task_id
            agent.last_heartbeat_at = now
            agent.metadata_json = {**agent.metadata_json, **(metadata_json or {})}

        db.commit()
        db.refresh(agent)
        AgentService._write_heartbeat(agent)
        return agent

    @staticmethod
    def list_agents(db: Session) -> list[Agent]:
        return list(db.scalars(select(Agent).order_by(Agent.name.asc())).all())

    @staticmethod
    def get_agent(db: Session, name: str) -> Agent | None:
        return db.scalar(select(Agent).where(Agent.name == name))

    @staticmethod
    def mark_task_state(db: Session, name: str, status: AgentStatus, current_task_id: str | None = None) -> Agent | None:
        agent = db.scalar(select(Agent).where(Agent.name == name))
        if agent is None:
            return None

        agent.status = status
        agent.current_task_id = current_task_id
        agent.last_heartbeat_at = utcnow()
        db.commit()
        db.refresh(agent)
        AgentService._write_heartbeat(agent)
        return agent

    @staticmethod
    def mark_stale_agents(db: Session) -> int:
        cutoff = utcnow() - timedelta(seconds=settings.agent_heartbeat_ttl_seconds)
        stale_agents = list(
            db.scalars(
                select(Agent).where(Agent.last_heartbeat_at < cutoff).where(Agent.status != AgentStatus.offline)
            ).all()
        )

        for agent in stale_agents:
            agent.status = AgentStatus.offline
            agent.current_task_id = None

        if stale_agents:
            db.commit()

        return len(stale_agents)

    @staticmethod
    def _write_heartbeat(agent: Agent) -> None:
        payload = {
            "name": agent.name,
            "status": agent.status.value,
            "current_task_id": agent.current_task_id,
            "last_heartbeat_at": agent.last_heartbeat_at.isoformat(),
            "metadata_json": agent.metadata_json,
        }
        redis_client.setex(
            AgentService._heartbeat_key(agent.name),
            settings.agent_heartbeat_ttl_seconds,
            json.dumps(payload),
        )

