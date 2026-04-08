from pydantic import BaseModel, Field


class ActiveModelConfig(BaseModel):
    provider: str
    model: str


class ModelOption(BaseModel):
    provider: str
    model: str
    label: str = ""
    summary: str = ""
    family: str = ""
    role_group: str = "general"
    role_group_label: str = "General"
    roles: list[str] = Field(default_factory=list)
    modality: str = "text"
    source: str = "local"
    speed: str = "balanced"
    resource_tier: str = "medium"
    cloud_auth_required: bool = False
    installed: bool = False
    configured: bool = False
    recommended: bool = False
    active: bool = False


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
    ollama_choices: list[ModelOption] = Field(default_factory=list)
    gemini_choices: list[ModelOption] = Field(default_factory=list)
