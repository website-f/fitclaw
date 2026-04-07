from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.database import session_scope
from app.services.agent_service import AgentService
from app.services.report_service import ReportService
from app.services.telegram_service import TelegramService

settings = get_settings()


@celery_app.task(name="app.workers.jobs.generate_daily_report")
def generate_daily_report() -> dict:
    with session_scope() as db:
        report = ReportService.generate_daily_report(db)
        delivered = False
        if settings.report_chat_enabled:
            delivered = TelegramService.send_message(settings.default_report_chat_id, report.content)
            report.delivered = delivered
            db.commit()
        return {"report_id": report.report_id, "delivered": delivered}


@celery_app.task(name="app.workers.jobs.capture_health_snapshot")
def capture_health_snapshot() -> dict:
    with session_scope() as db:
        report = ReportService.capture_health_snapshot(db)
        return {"report_id": report.report_id, "status": report.metadata_json.get("status", "unknown")}


@celery_app.task(name="app.workers.jobs.mark_stale_agents")
def mark_stale_agents() -> dict:
    with session_scope() as db:
        marked = AgentService.mark_stale_agents(db)
        return {"marked_offline": marked}

