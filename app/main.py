from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import init_db
from app.middleware.agent_auth import AgentBasicAuthMiddleware
from app.routers import agent_control, agent_tasks, agents, chat, device_control, health, models, tasks, uploads, web_app

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
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
app.include_router(models.router)
app.include_router(tasks.router)
app.include_router(agents.router)
app.include_router(agent_tasks.router)
app.include_router(agent_control.router)
app.include_router(device_control.router)
app.include_router(uploads.router)
app.include_router(web_app.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/", tags=["root"])
def read_root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "environment": settings.app_env,
        "docs": "/docs",
        "health": "/health",
        "control": "/control",
        "app": "/app",
        "version": "0.2.0",
    }
