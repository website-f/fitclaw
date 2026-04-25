"""Smart inbound router — classifies free-text messages and dispatches.

The single entry point is RouterService.classify(text), which calls the
local LLM with a structured-output prompt and returns a RouteIntent. The
caller (Telegram bot, WhatsApp adapter, web chat) decides whether to
dispatch directly based on confidence + supported categories.

This is the foundation for "stop typing /fix /push /deploy and just talk."
Future automations (CRM, finance, calendar, blog drafts, etc.) plug in
by adding a category here and a dispatcher in the caller.
"""
from fastapi import FastAPI

from app.modules.router import models as _models  # noqa: F401
from app.modules.router.api import router


def register(app: FastAPI) -> None:
    app.include_router(router)
