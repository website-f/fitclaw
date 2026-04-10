from datetime import datetime

from pydantic import BaseModel, Field


class MemoryCoreProfileUpdate(BaseModel):
    display_name: str | None = None
    about: str | None = None
    preferences: list[str] | None = None
    coding_preferences: list[str] | None = None
    workflow_preferences: list[str] | None = None
    notes: list[str] | None = None
    tags: list[str] | None = None


class MemoryCoreProfileResponse(BaseModel):
    user_id: str
    display_name: str | None = None
    about: str | None = None
    preferences: list[str] = Field(default_factory=list)
    coding_preferences: list[str] = Field(default_factory=list)
    workflow_preferences: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    updated_at: datetime


class MemoryCoreProjectUpsert(BaseModel):
    title: str | None = None
    summary: str | None = None
    root_hint: str | None = None
    repo_origin: str | None = None
    stack: list[str] | None = None
    goals: list[str] | None = None
    important_files: list[str] | None = None
    commands: list[str] | None = None
    structure: list[str] | None = None
    preferences: list[str] | None = None
    notes: list[str] | None = None
    tags: list[str] | None = None


class MemoryCoreProjectResponse(BaseModel):
    user_id: str
    project_key: str
    title: str
    summary: str = ""
    root_hint: str | None = None
    repo_origin: str | None = None
    stack: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    important_files: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    structure: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    updated_at: datetime


class MemoryCoreProjectSummaryResponse(BaseModel):
    project_key: str
    title: str
    summary: str = ""
    stack: list[str] = Field(default_factory=list)
    updated_at: datetime


class MemoryCoreMarkdownResponse(BaseModel):
    project_key: str
    markdown: str
