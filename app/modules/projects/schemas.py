from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProjectUpsert(BaseModel):
    slug: str = Field(..., min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")
    name: str
    description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    repo_url: str | None = None
    default_branch: str = "main"
    branches: list[str] = Field(default_factory=list)
    agent_name: str | None = None
    local_path: str | None = None
    vps_path: str | None = None
    deploy_command: str | None = None


class ProjectResponse(BaseModel):
    id: int
    slug: str
    name: str
    description: str | None
    keywords: list[str]
    repo_url: str | None
    default_branch: str
    branches: list[str]
    agent_name: str | None
    local_path: str | None
    vps_path: str | None
    deploy_command: str | None
    user_id: str
    created_at: datetime
    updated_at: datetime


class DeployRequest(BaseModel):
    branch: str | None = None
    note: str | None = None


class DeployResponse(BaseModel):
    project_slug: str
    branch: str | None
    started_at: datetime
    finished_at: datetime
    exit_code: int
    stdout: str
    stderr: str


class FixDispatchRequest(BaseModel):
    project_slug: str | None = None  # None → use matching
    issue_text: str
    raw_text: str | None = None  # full message for NL match


class FixDispatchResponse(BaseModel):
    matched_projects: list[ProjectResponse]
    task_id: str | None = None  # set when matched_projects has exactly one
    note: str
