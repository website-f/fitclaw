from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.memorycore import (
    MemoryCoreProfileResponse,
    MemoryCoreProfileUpdate,
    MemoryCoreProjectResponse,
    MemoryCoreProjectSummaryResponse,
    MemoryCoreProjectUpsert,
)
from app.services.memorycore_service import MemoryCoreService

router = APIRouter(prefix="/api/v1/memorycore", tags=["memorycore"])


@router.get("/profile", response_model=MemoryCoreProfileResponse)
def get_profile(user_id: str, db: Session = Depends(get_db)):
    profile = MemoryCoreService.get_profile(db, user_id=user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="MemoryCore profile not found.")
    return MemoryCoreProfileResponse(**profile)


@router.put("/profile", response_model=MemoryCoreProfileResponse)
def put_profile(user_id: str, payload: MemoryCoreProfileUpdate, db: Session = Depends(get_db)):
    profile = MemoryCoreService.upsert_profile(
        db,
        user_id=user_id,
        payload=payload.model_dump(exclude_unset=True),
    )
    return MemoryCoreProfileResponse(**profile)


@router.delete("/profile")
def delete_profile(user_id: str, db: Session = Depends(get_db)):
    deleted = MemoryCoreService.delete_profile(db, user_id=user_id)
    return {"deleted": deleted}


@router.get("/projects", response_model=list[MemoryCoreProjectSummaryResponse])
def list_projects(user_id: str, db: Session = Depends(get_db)):
    items = MemoryCoreService.list_projects(db, user_id=user_id)
    return [MemoryCoreProjectSummaryResponse(**item) for item in items]


@router.get("/download/launcher")
def download_launcher_bundle(
    user_id: str,
    server_url: str,
    wake_name: str = "jarvis",
    platform: str = "windows-x64",
):
    try:
        filename, payload = MemoryCoreService.build_launcher_bundle(
            server_url=server_url,
            user_id=user_id,
            wake_name=wake_name,
            platform=platform,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Length": str(len(payload)),
    }
    return Response(content=payload, media_type="application/zip", headers=headers)


@router.delete("/projects")
def delete_all_projects(user_id: str, db: Session = Depends(get_db)):
    deleted = MemoryCoreService.delete_all_projects(db, user_id=user_id)
    return {"deleted": deleted}


@router.get("/projects/{project_key}", response_model=MemoryCoreProjectResponse)
def get_project(project_key: str, user_id: str, db: Session = Depends(get_db)):
    item = MemoryCoreService.get_project(db, user_id=user_id, project_key=project_key)
    if item is None:
        raise HTTPException(status_code=404, detail="MemoryCore project memory not found.")
    return MemoryCoreProjectResponse(**item)


@router.put("/projects/{project_key}", response_model=MemoryCoreProjectResponse)
def put_project(project_key: str, user_id: str, payload: MemoryCoreProjectUpsert, db: Session = Depends(get_db)):
    item = MemoryCoreService.upsert_project(
        db,
        user_id=user_id,
        project_key=project_key,
        payload=payload.model_dump(exclude_unset=True),
    )
    return MemoryCoreProjectResponse(**item)


@router.get("/projects/{project_key}/markdown", response_class=PlainTextResponse)
def get_project_markdown(project_key: str, user_id: str, db: Session = Depends(get_db)):
    markdown = MemoryCoreService.render_project_markdown(db, user_id=user_id, project_key=project_key)
    if markdown is None:
        raise HTTPException(status_code=404, detail="MemoryCore project memory not found.")
    return PlainTextResponse(markdown)


@router.delete("/projects/{project_key}")
def delete_project(project_key: str, user_id: str, db: Session = Depends(get_db)):
    deleted = MemoryCoreService.delete_project(db, user_id=user_id, project_key=project_key)
    return {"deleted": deleted}


@router.delete("/")
def clear_memorycore(user_id: str, db: Session = Depends(get_db)):
    return MemoryCoreService.clear_all(db, user_id=user_id)
