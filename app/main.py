from pathlib import Path
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.middleware.agent_auth import AgentBasicAuthMiddleware
from app.routers import agent_control, agent_tasks, agents, calendar, chat, device_control, downloads, finance, health, memorycore, models, tasks, transit, uploads, weather, web_app, whatsapp
from app.services.runtime_config_service import RuntimeConfigService

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.3.33",
    description="Self-hosted personal AI ops platform with Telegram, agent APIs, and background workers.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AgentBasicAuthMiddleware)

app.mount(
    "/app-assets",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "ui" / "pwa" / "assets")),
    name="app-assets",
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(calendar.router)
app.include_router(finance.router)
app.include_router(weather.router)
app.include_router(transit.router)
app.include_router(memorycore.router)
app.include_router(models.router)
app.include_router(tasks.router)
app.include_router(agents.router)
app.include_router(agent_tasks.router)
app.include_router(agent_control.router)
app.include_router(device_control.router)
app.include_router(uploads.router)
app.include_router(web_app.router)
app.include_router(whatsapp.router)
app.include_router(downloads.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    if settings.ollama_preload_active_model_on_startup:
        threading.Thread(target=_prewarm_startup_models, name="fitclaw-ollama-prewarm", daemon=True).start()


def _prewarm_startup_models() -> None:
    db = SessionLocal()
    try:
        active = RuntimeConfigService.get_active_llm(db)
    finally:
        db.close()

    if active.get("provider") != "ollama":
        return

    model_name = str(active.get("model", "")).strip()
    prewarm_candidates: list[tuple[str, bool]] = []
    if model_name:
        profile = RuntimeConfigService.get_model_profile("ollama", model_name)
        prewarm_candidates.append((model_name, bool(profile and profile.modality == "vision")))

    fast_vision_model = RuntimeConfigService.get_preferred_fast_vision_model(
        active_provider=active.get("provider"),
        active_model=active.get("model"),
    )
    if fast_vision_model and fast_vision_model != model_name:
        prewarm_candidates.append((fast_vision_model, True))

    seen: set[str] = set()
    for candidate_model, vision in prewarm_candidates:
        if not candidate_model or candidate_model in seen:
            continue
        seen.add(candidate_model)
        try:
            RuntimeConfigService.prewarm_ollama_model(candidate_model, vision=vision)
        except Exception:
            continue


@app.get("/version", tags=["root"])
def read_version() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "environment": settings.app_env,
        "docs": "/docs",
        "health": "/health",
        "control": "/control",
        "app": "/app",
        "memorycore": "/memorycore",
        "finance": "/finance",
        "transit_live": "/transit-live",
        "whatsapp_beta": "/whatsapp-beta",
        "version": "0.3.33",
    }
