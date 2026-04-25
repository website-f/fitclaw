"""Projects module — registry of code projects spread across PC + VPS.

A `Project` row holds enough metadata to drive the full Telegram → fix → push
→ deploy loop universally:

- repo_url, default_branch, branches  → for git operations
- agent_name, local_path              → tells the PC agent where to work
- vps_path, deploy_command            → tells the VPS how to redeploy

NL resolution: `match_by_text("fix the button on fitclaw")` walks the keywords
list of every project and returns the best matches. No ML needed for v1.
"""
from fastapi import FastAPI

from app.modules.projects import models as _models  # noqa: F401
from app.modules.projects.api import router


def register(app: FastAPI) -> None:
    app.include_router(router)
