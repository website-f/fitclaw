from pathlib import Path
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.middleware.agent_auth import AgentBasicAuthMiddleware
from app.routers import agent_control, agent_tasks, agents, calendar, chat, device_control, finance, health, memorycore, models, tasks, transit, uploads, weather, web_app, whatsapp
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


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    if settings.ollama_preload_active_model_on_startup:
        threading.Thread(target=_prewarm_active_model, name="fitclaw-ollama-prewarm", daemon=True).start()


def _prewarm_active_model() -> None:
    db = SessionLocal()
    try:
        active = RuntimeConfigService.get_active_llm(db)
    finally:
        db.close()

    if active.get("provider") != "ollama":
        return

    model_name = str(active.get("model", "")).strip()
    if not model_name:
        return

    try:
        profile = RuntimeConfigService.get_model_profile("ollama", model_name)
        RuntimeConfigService.prewarm_ollama_model(model_name, bool(profile and profile.modality == "vision"))
    except Exception:
        return


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
