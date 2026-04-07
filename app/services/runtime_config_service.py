import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.setting import AppSetting

settings = get_settings()


class RuntimeConfigService:
    ACTIVE_LLM_KEY = "active_llm"

    @staticmethod
    def get_default_llm() -> dict[str, str]:
        return {"provider": "ollama", "model": settings.ollama_model}

    @staticmethod
    def get_active_llm(db: Session) -> dict[str, str]:
        record = db.scalar(select(AppSetting).where(AppSetting.key == RuntimeConfigService.ACTIVE_LLM_KEY))
        if record and record.value_json.get("provider") and record.value_json.get("model"):
            return {
                "provider": str(record.value_json["provider"]),
                "model": str(record.value_json["model"]),
            }
        return RuntimeConfigService.get_default_llm()

    @staticmethod
    def set_active_llm(db: Session, provider: str, model: str) -> dict[str, str]:
        record = db.scalar(select(AppSetting).where(AppSetting.key == RuntimeConfigService.ACTIVE_LLM_KEY))
        payload = {"provider": provider.strip(), "model": model.strip()}

        if record is None:
            record = AppSetting(key=RuntimeConfigService.ACTIVE_LLM_KEY, value_json=payload)
            db.add(record)
        else:
            record.value_json = payload

        db.commit()
        return payload

    @staticmethod
    def list_ollama_models() -> list[str]:
        api_base = settings.ollama_base_url.rstrip("/")
        try:
            response = httpx.get(f"{api_base}/api/tags", timeout=15)
            response.raise_for_status()
            data = response.json()
            models = data.get("models", [])
            names = [item.get("name", "").strip() for item in models if item.get("name")]
            return sorted(set(names))
        except Exception:
            pass

        try:
            response = httpx.get(f"{api_base}/v1/models", timeout=15)
            response.raise_for_status()
            data = response.json()
            models = data.get("data", [])
            names = [item.get("id", "").strip() for item in models if item.get("id")]
            return sorted(set(names))
        except Exception:
            return []

    @staticmethod
    def pull_ollama_model(model: str) -> None:
        response = httpx.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/pull",
            json={"name": model, "stream": False},
            timeout=max(settings.ollama_request_timeout, 600),
        )
        response.raise_for_status()

    @staticmethod
    def validate_provider_model(provider: str, model: str) -> tuple[str, str]:
        provider_name = provider.strip().lower()
        model_name = model.strip()
        if provider_name not in {"ollama", "gemini"}:
            raise ValueError("Provider must be either 'ollama' or 'gemini'.")
        if not model_name:
            raise ValueError("Model name cannot be empty.")
        if provider_name == "gemini" and not settings.gemini_enabled:
            raise ValueError("Gemini is not enabled. Set GEMINI_API_KEY first.")
        return provider_name, model_name
