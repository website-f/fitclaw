from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.agent_download_service import AgentDownloadService

router = APIRouter(prefix="/api/v1/downloads", tags=["downloads"])


@router.get("/agents")
def list_agent_downloads():
    return {"downloads": AgentDownloadService.list_downloads()}


@router.get("/agents/{platform}")
def download_agent_installer(platform: str):
    try:
        artifact, config = AgentDownloadService.get_download(platform)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown download target.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        artifact,
        media_type=config["media_type"],
        filename=artifact.name,
    )
