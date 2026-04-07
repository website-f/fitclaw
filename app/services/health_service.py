import httpx
import redis
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine

settings = get_settings()
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


class HealthService:
    @staticmethod
    def snapshot() -> dict:
        services = {
            "database": "down",
            "redis": "down",
            "ollama": "down",
        }
        detail: dict[str, str] = {
            "ollama_model": settings.ollama_model,
            "environment": settings.app_env,
        }

        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            services["database"] = "up"
        except Exception as exc:
            detail["database_error"] = str(exc)

        try:
            if redis_client.ping():
                services["redis"] = "up"
        except Exception as exc:
            detail["redis_error"] = str(exc)

        try:
            response = httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=10)
            response.raise_for_status()
            services["ollama"] = "up"
        except Exception as exc:
            detail["ollama_error"] = str(exc)

        overall_status = "ok" if all(value == "up" for value in services.values()) else "degraded"
        return {"status": overall_status, "services": services, "detail": detail}

