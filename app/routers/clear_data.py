from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/clear-data", tags=["clear-data"])

DATA_ROOT = Path("/data")

CATEGORIES: dict[str, dict] = {
    "calendar_invites": {
        "label": "Calendar invites",
        "description": "Generated .ics files for meetings and reminders.",
        "path": DATA_ROOT / "calendar_invites",
        "recursive": False,
    },
    "device_artifacts": {
        "label": "Device artifacts",
        "description": "Screenshots and command outputs captured from registered agents.",
        "path": DATA_ROOT / "device_artifacts",
        "recursive": True,
    },
    "tmp_tests": {
        "label": "Temp test files",
        "description": "Scratch files left behind by local test runs.",
        "path": DATA_ROOT / "tmp-tests",
        "recursive": False,
    },
    "uploads": {
        "label": "Uploaded files",
        "description": "User-submitted chat attachments stored on disk (the DB records stay).",
        "path": DATA_ROOT / "uploads",
        "recursive": True,
    },
}


class DeleteRequest(BaseModel):
    names: list[str] = Field(default_factory=list)


class CategoryItem(BaseModel):
    name: str
    is_dir: bool
    size_bytes: int
    modified_at: float | None


class CategorySummary(BaseModel):
    key: str
    label: str
    description: str
    path: str
    total_bytes: int
    item_count: int
    exists: bool
    items: list[CategoryItem]


def _iter_top_entries(category_path: Path, recursive: bool):
    if not category_path.exists() or not category_path.is_dir():
        return
    for entry in sorted(category_path.iterdir(), key=lambda p: p.name.lower()):
        try:
            if entry.is_dir():
                size = _dir_size(entry) if recursive else sum(
                    (child.stat().st_size for child in entry.iterdir() if child.is_file()),
                    0,
                )
            else:
                size = entry.stat().st_size
            modified_at = entry.stat().st_mtime
        except OSError:
            size = 0
            modified_at = None
        yield CategoryItem(
            name=entry.name,
            is_dir=entry.is_dir(),
            size_bytes=int(size),
            modified_at=modified_at,
        )


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in _safe_walk(path):
        for filename in files:
            try:
                total += (root / filename).stat().st_size
            except OSError:
                continue
    return total


def _safe_walk(path: Path):
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        files = [entry.name for entry in entries if entry.is_file()]
        dirs = [entry for entry in entries if entry.is_dir()]
        yield current, [d.name for d in dirs], files
        stack.extend(dirs)


def _resolve_category(key: str) -> dict:
    meta = CATEGORIES.get(key)
    if not meta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown category `{key}`.")
    return meta


def _safe_child(category_path: Path, name: str) -> Path:
    candidate = (category_path / name).resolve()
    try:
        candidate.relative_to(category_path.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid entry name.") from exc
    return candidate


def _remove_entry(entry: Path) -> None:
    if entry.is_dir() and not entry.is_symlink():
        shutil.rmtree(entry, ignore_errors=True)
    else:
        try:
            entry.unlink(missing_ok=True)
        except OSError:
            pass


@router.get("", response_model=list[CategorySummary])
def list_categories(preview_limit: int = 200):
    preview_limit = max(1, min(preview_limit, 1000))
    summaries: list[CategorySummary] = []
    for key, meta in CATEGORIES.items():
        category_path = meta["path"]
        exists = category_path.exists() and category_path.is_dir()
        items: list[CategoryItem] = []
        total_bytes = 0
        count = 0
        if exists:
            for item in _iter_top_entries(category_path, meta["recursive"]):
                total_bytes += item.size_bytes
                count += 1
                if len(items) < preview_limit:
                    items.append(item)
        summaries.append(
            CategorySummary(
                key=key,
                label=meta["label"],
                description=meta["description"],
                path=str(category_path),
                total_bytes=total_bytes,
                item_count=count,
                exists=exists,
                items=items,
            )
        )
    return summaries


@router.get("/{category}", response_model=CategorySummary)
def get_category(category: str, preview_limit: int = 2000):
    meta = _resolve_category(category)
    category_path: Path = meta["path"]
    exists = category_path.exists() and category_path.is_dir()
    items: list[CategoryItem] = []
    total_bytes = 0
    count = 0
    preview_limit = max(1, min(preview_limit, 10000))
    if exists:
        for item in _iter_top_entries(category_path, meta["recursive"]):
            total_bytes += item.size_bytes
            count += 1
            if len(items) < preview_limit:
                items.append(item)
    return CategorySummary(
        key=category,
        label=meta["label"],
        description=meta["description"],
        path=str(category_path),
        total_bytes=total_bytes,
        item_count=count,
        exists=exists,
        items=items,
    )


@router.post("/{category}/delete")
def delete_entries(category: str, payload: DeleteRequest):
    meta = _resolve_category(category)
    category_path: Path = meta["path"]
    if not payload.names:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide at least one entry name.")
    deleted: list[str] = []
    for name in payload.names:
        if not name or "/" in name or "\\" in name or name in {".", ".."}:
            continue
        target = _safe_child(category_path, name)
        if not target.exists():
            continue
        _remove_entry(target)
        deleted.append(name)
    return {"category": category, "deleted": deleted, "deleted_count": len(deleted)}


@router.delete("/{category}")
def clear_category(category: str):
    meta = _resolve_category(category)
    category_path: Path = meta["path"]
    removed = 0
    if category_path.exists() and category_path.is_dir():
        for entry in list(category_path.iterdir()):
            _remove_entry(entry)
            removed += 1
    return {"category": category, "deleted_count": removed}
