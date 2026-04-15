import json
from datetime import timedelta

import redis
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.agent import Agent, AgentStatus
from app.models.base import utcnow
from app.models.device_command import DeviceCommand, DeviceCommandStatus
from app.models.task import Task, TaskStatus
from app.schemas.agent import AgentResponse
from app.schemas.model import ActiveModelConfig
from app.services.runtime_config_service import RuntimeConfigService

settings = get_settings()
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


class AgentService:
    MODEL_PREFS_KEY = "model_preferences"

    @staticmethod
    def _heartbeat_key(name: str) -> str:
        return f"agent:heartbeat:{name}"

    @staticmethod
    def register_agent(
        db: Session, name: str, capabilities_json: list[str] | None = None, metadata_json: dict | None = None
    ) -> Agent:
        agent = db.scalar(select(Agent).where(Agent.name == name))
        now = utcnow()
        previous_status = agent.status if agent is not None else None

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
        if previous_status == AgentStatus.offline:
            AgentService._queue_whatsapp_status_alert(agent.name, "online", "Agent re-registered and is reachable again.")
        return agent

    @staticmethod
    def heartbeat(
        db: Session, name: str, status: AgentStatus = AgentStatus.online, current_task_id: str | None = None, metadata_json: dict | None = None
    ) -> Agent:
        agent = db.scalar(select(Agent).where(Agent.name == name))
        now = utcnow()
        previous_status = agent.status if agent is not None else None

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
        if previous_status == AgentStatus.offline and status != AgentStatus.offline:
            AgentService._queue_whatsapp_status_alert(agent.name, status.value, "Heartbeat resumed and the agent is back online.")
        return agent

    @staticmethod
    def list_agents(db: Session) -> list[Agent]:
        return list(db.scalars(select(Agent).order_by(Agent.name.asc())).all())

    @staticmethod
    def get_agent(db: Session, name: str) -> Agent | None:
        return db.scalar(select(Agent).where(Agent.name == name))

    @staticmethod
    def delete_agent(db: Session, name: str, purge_related: bool = False) -> dict | None:
        agent = db.scalar(select(Agent).where(Agent.name == name))
        if agent is None:
            return None

        pending_tasks_updated = 0
        pending_commands_deleted = 0
        if purge_related:
            pending_tasks = list(
                db.scalars(
                    select(Task)
                    .where(Task.assigned_agent_name == name)
                    .where(Task.status.in_([TaskStatus.pending, TaskStatus.in_progress]))
                ).all()
            )
            for task in pending_tasks:
                task.assigned_agent_name = None
                task.metadata_json = {
                    **(task.metadata_json or {}),
                    "agent_removed": True,
                    "previous_agent_name": name,
                }
                if task.status == TaskStatus.in_progress:
                    task.status = TaskStatus.failed
                    task.error_text = "Agent was removed before the task could finish."
                    task.completed_at = utcnow()
                pending_tasks_updated += 1

            delete_result = db.execute(
                delete(DeviceCommand)
                .where(DeviceCommand.agent_name == name)
                .where(DeviceCommand.status.in_([DeviceCommandStatus.pending, DeviceCommandStatus.running]))
            )
            pending_commands_deleted = int(delete_result.rowcount or 0)

        db.delete(agent)
        db.commit()
        redis_client.delete(AgentService._heartbeat_key(name))
        return {
            "name": name,
            "purge_related": purge_related,
            "pending_tasks_updated": pending_tasks_updated,
            "pending_commands_deleted": pending_commands_deleted,
        }

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
        cutoff = AgentService._stale_cutoff()
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
    def _stale_cutoff():
        return utcnow() - timedelta(seconds=settings.agent_heartbeat_ttl_seconds)

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

    @staticmethod
    def _queue_whatsapp_status_alert(agent_name: str, status: str, detail: str) -> None:
        try:
            from app.core.database import SessionLocal
            from app.services.whatsapp_service import WhatsAppBetaService

            db = SessionLocal()
            try:
                WhatsAppBetaService.queue_agent_alert(db, agent_name, status, detail)
            finally:
                db.close()
        except Exception:
            return

    @staticmethod
    def get_model_preferences(agent: Agent) -> dict:
        raw = (agent.metadata_json or {}).get(AgentService.MODEL_PREFS_KEY, {})
        if not isinstance(raw, dict):
            raw = {}
        preferred_text = AgentService._normalize_model_ref(raw.get("preferred_text"))
        preferred_vision = AgentService._normalize_model_ref(raw.get("preferred_vision"))
        allowed_models = AgentService._normalize_model_ref_list(raw.get("allowed_models"))
        if not allowed_models:
            allowed_models = RuntimeConfigService.get_available_model_refs()
        return {
            "preferred_text": preferred_text,
            "preferred_vision": preferred_vision,
            "allowed_models": allowed_models,
        }

    @staticmethod
    def update_model_preferences(
        db: Session,
        name: str,
        preferred_text: dict | None = None,
        preferred_vision: dict | None = None,
        allowed_models: list[dict] | None = None,
    ) -> Agent | None:
        agent = db.scalar(select(Agent).where(Agent.name == name))
        if agent is None:
            return None

        current_metadata = dict(agent.metadata_json or {})
        current = AgentService.get_model_preferences(agent)
        merged = {
            "preferred_text": AgentService._normalize_model_ref(
                preferred_text if preferred_text is not None else current.get("preferred_text")
            ),
            "preferred_vision": AgentService._normalize_model_ref(
                preferred_vision if preferred_vision is not None else current.get("preferred_vision")
            ),
            "allowed_models": AgentService._normalize_model_ref_list(
                allowed_models if allowed_models is not None else current.get("allowed_models", [])
            ),
        }

        current_metadata[AgentService.MODEL_PREFS_KEY] = merged
        agent.metadata_json = current_metadata
        agent.updated_at = utcnow()
        db.commit()
        db.refresh(agent)
        AgentService._write_heartbeat(agent)
        return agent

    @staticmethod
    def serialize_agent(agent: Agent) -> AgentResponse:
        preferences = AgentService.get_model_preferences(agent)
        preferred_text = preferences.get("preferred_text")
        preferred_vision = preferences.get("preferred_vision")
        allowed_models = preferences.get("allowed_models", [])
        return AgentResponse(
            name=agent.name,
            status=agent.status,
            capabilities_json=list(agent.capabilities_json or []),
            metadata_json=dict(agent.metadata_json or {}),
            last_heartbeat_at=agent.last_heartbeat_at,
            current_task_id=agent.current_task_id,
            registered_at=agent.registered_at,
            updated_at=agent.updated_at,
            model_preferences={
                "preferred_text": ActiveModelConfig(**preferred_text) if preferred_text else None,
                "preferred_vision": ActiveModelConfig(**preferred_vision) if preferred_vision else None,
                "allowed_models": [ActiveModelConfig(**item) for item in allowed_models],
            },
        )

    @staticmethod
    def _normalize_model_ref(value) -> dict | None:
        if isinstance(value, ActiveModelConfig):
            provider = value.provider.strip().lower()
            model = value.model.strip()
        elif isinstance(value, dict):
            provider = str(value.get("provider", "ollama")).strip().lower()
            model = str(value.get("model", "")).strip()
        else:
            return None

        if provider not in {"ollama", "gemini"} or not model:
            return None
        return {"provider": provider, "model": model}

    @staticmethod
    def _normalize_model_ref_list(values) -> list[dict]:
        results: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for item in values or []:
            normalized = AgentService._normalize_model_ref(item)
            if normalized is None:
                continue
            key = (normalized["provider"], normalized["model"])
            if key in seen:
                continue
            seen.add(key)
            results.append(normalized)
        return results
