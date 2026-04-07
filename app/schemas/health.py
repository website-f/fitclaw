from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    services: dict[str, str] = Field(default_factory=dict)
    detail: dict = Field(default_factory=dict)

