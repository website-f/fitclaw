from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.database import session_scope
from app.models.agent import Agent, AgentStatus
from app.services.agent_service import AgentService
from app.services.report_service import ReportService
from app.services.telegram_service import TelegramService
from app.services.whatsapp_service import WhatsAppBetaService
from sqlalchemy import select

settings = get_settings()


@celery_app.task(name="app.workers.jobs.generate_daily_report")
def generate_daily_report() -> dict:
    with session_scope() as db:
        report = ReportService.generate_daily_report(db)
        delivered = False
        whatsapp_delivered = False
        if settings.report_chat_enabled:
            delivered = TelegramService.send_message(settings.default_report_chat_id, report.content)
            report.delivered = delivered
        whatsapp_delivered = WhatsAppBetaService.queue_daily_report(db, report.content)
        db.commit()
        return {
            "report_id": report.report_id,
            "delivered": delivered,
            "whatsapp_queued": whatsapp_delivered,
        }


@celery_app.task(name="app.workers.jobs.capture_health_snapshot")
def capture_health_snapshot() -> dict:
    with session_scope() as db:
        report = ReportService.capture_health_snapshot(db)
        return {"report_id": report.report_id, "status": report.metadata_json.get("status", "unknown")}


@celery_app.task(name="app.workers.jobs.mark_stale_agents")
def mark_stale_agents() -> dict:
    with session_scope() as db:
        cutoff_agents = list(
            db.scalars(
                select(Agent).where(Agent.last_heartbeat_at < (AgentService._stale_cutoff())).where(Agent.status != AgentStatus.offline)
            ).all()
        )
        marked = AgentService.mark_stale_agents(db)
        if marked:
            for agent in cutoff_agents:
                WhatsAppBetaService.queue_agent_alert(
                    db,
                    agent.name,
                    "offline",
                    "Heartbeat expired. The platform marked this agent offline.",
                )
        return {"marked_offline": marked}


@celery_app.task(name="app.workers.jobs.poll_whatsapp_inbox")
def poll_whatsapp_inbox() -> dict:
    with session_scope() as db:
        result = WhatsAppBetaService.process_inbound_messages(db)
        return result


@celery_app.task(name="app.workers.jobs.process_whatsapp_inbound_message")
def process_whatsapp_inbound_message(
    message_id: str,
    chat_jid: str,
    sender: str,
    content: str,
    media_type: str = "",
    filename: str = "",
) -> dict:
    with session_scope() as db:
        result = WhatsAppBetaService.process_inbound_message(
            db,
            message_id=message_id,
            chat_jid=chat_jid,
            sender=sender,
            content=content,
            media_type=media_type,
            filename=filename,
        )
        return result


@celery_app.task(name="app.workers.jobs.send_whatsapp_message")
def send_whatsapp_message(
    recipient: str,
    message: str,
    category: str = "general",
    bypass_cooldown: bool = False,
) -> dict:
    with session_scope() as db:
        success, detail = WhatsAppBetaService.send_message_now(
            db,
            recipient=recipient,
            message=message,
            category=category,
            bypass_cooldown=bypass_cooldown,
        )
        return {
            "success": success,
            "recipient": recipient,
            "category": category,
            "detail": detail,
        }
