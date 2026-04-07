from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings
from app.core.database import init_db

settings = get_settings()
init_db()


def parse_cron_expression(expression: str) -> crontab:
    fields = expression.strip().split()
    if len(fields) != 5:
        raise ValueError("DAILY_REPORT_CRON must contain exactly five cron fields.")

    minute, hour, day_of_month, month_of_year, day_of_week = fields
    return crontab(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
    )


celery_app = Celery(
    "personal_ai_ops",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.jobs"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.timezone,
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "generate-daily-report": {
            "task": "app.workers.jobs.generate_daily_report",
            "schedule": parse_cron_expression(settings.daily_report_cron),
        },
        "capture-health-snapshot": {
            "task": "app.workers.jobs.capture_health_snapshot",
            "schedule": float(settings.health_report_interval_seconds),
        },
        "mark-stale-agents": {
            "task": "app.workers.jobs.mark_stale_agents",
            "schedule": float(max(settings.agent_heartbeat_ttl_seconds // 2, 30)),
        },
    },
)

