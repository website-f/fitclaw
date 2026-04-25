from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.projects.schemas import (
    DeployRequest,
    DeployResponse,
    ProjectResponse,
    ProjectUpsert,
)
from app.modules.projects.service import ProjectService

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.put("/{slug}", response_model=ProjectResponse)
def upsert_project(
    slug: str,
    user_id: str,
    payload: ProjectUpsert,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    if payload.slug != slug:
        raise HTTPException(status_code=400, detail="URL slug must match payload slug")
    row = ProjectService.upsert(db, user_id, payload)
    return ProjectResponse.model_validate(row, from_attributes=True)


@router.get("", response_model=list[ProjectResponse])
def list_projects(user_id: str, db: Session = Depends(get_db)) -> list[ProjectResponse]:
    rows = ProjectService.list(db, user_id)
    return [ProjectResponse.model_validate(r, from_attributes=True) for r in rows]


@router.get("/match", response_model=list[ProjectResponse])
def match_projects(user_id: str, q: str, db: Session = Depends(get_db)) -> list[ProjectResponse]:
    rows = ProjectService.match_by_text(db, user_id, q)
    return [ProjectResponse.model_validate(r, from_attributes=True) for r in rows]


@router.get("/{slug}", response_model=ProjectResponse)
def get_project(slug: str, user_id: str, db: Session = Depends(get_db)) -> ProjectResponse:
    row = ProjectService.get_by_slug(db, user_id, slug)
    if row is None:
        raise HTTPException(status_code=404, detail=f"project '{slug}' not found")
    return ProjectResponse.model_validate(row, from_attributes=True)


@router.delete("/{slug}")
def delete_project(slug: str, user_id: str, db: Session = Depends(get_db)) -> dict:
    return {"deleted": ProjectService.delete(db, user_id, slug)}


@router.post("/{slug}/deploy", response_model=DeployResponse)
def deploy_project(
    slug: str,
    user_id: str,
    payload: DeployRequest | None = None,
    db: Session = Depends(get_db),
) -> DeployResponse:
    branch = payload.branch if payload else None
    try:
        return ProjectService.run_deploy(db, user_id, slug, branch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
