from pydantic import BaseModel, Field


class ActiveModelConfig(BaseModel):
    provider: str
    model: str


class ModelSelectRequest(BaseModel):
    provider: str = Field(default="ollama", min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=120)
    auto_pull: bool = True


class ModelListResponse(BaseModel):
    active: ActiveModelConfig
    defaults: ActiveModelConfig
    fallback_gemini_model: str | None = None
    installed_ollama_models: list[str] = Field(default_factory=list)
    configured_ollama_models: list[str] = Field(default_factory=list)

