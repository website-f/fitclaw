from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.model import ActiveModelConfig, ModelListResponse, ModelSelectRequest
from app.services.runtime_config_service import RuntimeConfigService

router = APIRouter(prefix="/api/v1/models", tags=["models"])
settings = get_settings()


@router.get("", response_model=ModelListResponse)
def list_models(db: Session = Depends(get_db)):
    active = RuntimeConfigService.get_active_llm(db)
    defaults = RuntimeConfigService.get_default_llm()
    installed = RuntimeConfigService.list_ollama_models()
    return ModelListResponse(
        active=ActiveModelConfig(**active),
        defaults=ActiveModelConfig(**defaults),
        fallback_gemini_model=settings.gemini_model if settings.gemini_enabled else None,
        installed_ollama_models=installed,
        configured_ollama_models=settings.ollama_model_list,
    )


@router.post("/select", response_model=ActiveModelConfig)
def select_model(payload: ModelSelectRequest, db: Session = Depends(get_db)):
    try:
        provider, model = RuntimeConfigService.validate_provider_model(payload.provider, payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if provider == "ollama":
        installed = RuntimeConfigService.list_ollama_models()
        if model not in installed:
            if not payload.auto_pull:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ollama model `{model}` is not installed. Enable auto_pull or pull it first.",
                )
            try:
                RuntimeConfigService.pull_ollama_model(model)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to pull Ollama model `{model}`: {exc}",
                ) from exc

    active = RuntimeConfigService.set_active_llm(db, provider=provider, model=model)
    return ActiveModelConfig(**active)

