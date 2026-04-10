from datetime import datetime

from pydantic import BaseModel, Field


class MemoryCoreProfileUpdate(BaseModel):
    display_name: str | None = None
    about: str | None = None
    preferences: list[str] | None = None
    coding_preferences: list[str] | None = None
    workflow_preferences: list[str] | None = None
    identity_notes: list[str] | None = None
    relationship_notes: list[str] | None = None
    standing_instructions: list[str] | None = None
    notes: list[str] | None = None
    tags: list[str] | None = None


class MemoryCoreProfileResponse(BaseModel):
    user_id: str
    display_name: str | None = None
    about: str | None = None
    preferences: list[str] = Field(default_factory=list)
    coding_preferences: list[str] = Field(default_factory=list)
    workflow_preferences: list[str] = Field(default_factory=list)
    identity_notes: list[str] = Field(default_factory=list)
    relationship_notes: list[str] = Field(default_factory=list)
    standing_instructions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    updated_at: datetime


class MemoryCoreProjectUpsert(BaseModel):
    title: str | None = None
    summary: str | None = None
    status: str | None = None
    root_hint: str | None = None
    repo_origin: str | None = None
    current_focus: str | None = None
    session_brief: str | None = None
    stack: list[str] | None = None
    goals: list[str] | None = None
    next_steps: list[str] | None = None
    reminders: list[str] | None = None
    decisions: list[str] | None = None
    observations: list[str] | None = None
    library_items: list[str] | None = None
    open_questions: list[str] | None = None
    recent_changes: list[str] | None = None
    skills: list[str] | None = None
    activity_log: list[dict[str, str]] | None = None
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
    status: str = "active"
    root_hint: str | None = None
    repo_origin: str | None = None
    current_focus: str | None = None
    session_brief: str | None = None
    stack: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    reminders: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    library_items: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    recent_changes: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    activity_log: list[dict[str, str]] = Field(default_factory=list)
    important_files: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    structure: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    last_opened_at: datetime | None = None
    open_count: int = 0
    updated_at: datetime


class MemoryCoreProjectSummaryResponse(BaseModel):
    project_key: str
    title: str
    summary: str = ""
    status: str = "active"
    current_focus: str | None = None
    session_brief: str | None = None
    stack: list[str] = Field(default_factory=list)
    next_steps_count: int = 0
    reminders_count: int = 0
    decisions_count: int = 0
    library_items_count: int = 0
    open_questions_count: int = 0
    last_opened_at: datetime | None = None
    open_count: int = 0
    updated_at: datetime


class MemoryCoreMarkdownResponse(BaseModel):
    project_key: str
    markdown: str


class MemoryCoreProjectStatusUpdate(BaseModel):
    status: str


class MemoryCoreSessionBriefingResponse(BaseModel):
    project_key: str
    title: str
    briefing: str


class MemoryCoreImportResponse(BaseModel):
    project_key: str
    title: str
    imported_fields: list[str] = Field(default_factory=list)


class MemoryCoreLibraryTemplateResponse(BaseModel):
    template_key: str
    title: str
    category: str
    summary: str
    current_focus: str | None = None
    session_brief: str | None = None
    library_items: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    reminders: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
