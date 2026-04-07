from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Personal AI Ops Platform"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    api_port: int = 8000
    timezone: str = "Asia/Kuala_Lumpur"

    database_url: str = "sqlite:////data/ai_ops.db"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    telegram_bot_token: str = ""
    telegram_allowed_user_ids: str = ""
    default_report_chat_id: str = ""

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_models: str = "qwen2.5:3b"
    ollama_vision_model: str = "gemma3:4b"
    ollama_vision_models: str = ""
    ollama_request_timeout: int = 120

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_vision_model: str = "gemini-2.5-flash"

    llm_temperature: float = 0.1
    memory_window: int = 12
    system_prompt: str = Field(
        default=(
            "You are my personal AI operations brain. "
            "Help me reason clearly, manage tasks, and coordinate trusted agents "
            "across my devices. When a user message is a task command, acknowledge "
            "the task state clearly and concisely."
        )
    )

    agent_basic_auth_username: str = "agent"
    agent_api_shared_key: str = "change-me-now"
    agent_heartbeat_ttl_seconds: int = 120
    health_report_interval_seconds: int = 600
    daily_report_cron: str = "0 8 * * *"

    flower_port: int = 5555
    ollama_port: int = 11434
    redis_port: int = 6379
    n8n_port: int = 5678
    n8n_encryption_key: str = "replace-with-a-long-random-string"
    n8n_host: str = "localhost"
    n8n_basic_auth_active: bool = True
    n8n_basic_auth_user: str = "admin"
    n8n_basic_auth_password: str = "change-this-n8n-password"
    upload_max_bytes: int = 15728640
    upload_extract_text_chars: int = 24000

    @property
    def telegram_allowed_user_id_set(self) -> set[int]:
        raw_values = [item.strip() for item in self.telegram_allowed_user_ids.split(",")]
        return {int(item) for item in raw_values if item}

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def report_chat_enabled(self) -> bool:
        return bool(self.default_report_chat_id and self.telegram_bot_token)

    @property
    def ollama_model_list(self) -> list[str]:
        values = [item.strip() for item in self.ollama_models.split(",")]
        return [item for item in values if item]

    @property
    def ollama_vision_model_list(self) -> list[str]:
        values = [item.strip() for item in self.ollama_vision_models.split(",")]
        return [item for item in values if item]


@lru_cache
def get_settings() -> Settings:
    return Settings()
