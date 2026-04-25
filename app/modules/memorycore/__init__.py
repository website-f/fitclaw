"""MemoryCore v2 module — usage ledger + design library.

Scope:
- Usage ledger: track token & cost across Claude Code / Codex / API calls.
- Design library: save frontend design references (prompt + tags + image paths)
  so Claude can recall them on request.

The original profile/project MemoryCore still lives in app.services.memorycore_service
and app.routers.memorycore. This module adds new endpoints alongside; it does
not replace the old ones.
"""
from fastapi import FastAPI

from app.modules.memorycore import models as _models  # noqa: F401  registers ORM classes
from app.modules.memorycore.api import router


def register(app: FastAPI) -> None:
    app.include_router(router)
