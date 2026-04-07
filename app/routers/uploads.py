from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.upload import UploadedAssetResponse
from app.services.upload_service import UploadService

router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])


@router.post("", response_model=UploadedAssetResponse, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    user_id: str = Form(...),
    session_id: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    raw_bytes = await file.read()
    try:
        asset = UploadService.create_asset_from_bytes(
            db=db,
            platform_user_id=user_id,
            session_id=session_id,
            source="web_upload",
            original_filename=file.filename or "upload.bin",
            mime_type=file.content_type,
            raw_bytes=raw_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return UploadedAssetResponse(
        asset_id=asset.asset_id,
        kind=asset.kind,
        original_filename=asset.original_filename,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        created_at=asset.created_at,
        public_url=UploadService.build_public_url(asset),
    )


@router.get("/{asset_id}", include_in_schema=False)
def get_uploaded_asset(asset_id: str, token: str = Query(...), db: Session = Depends(get_db)):
    asset = UploadService.get_asset(db, asset_id)
    if asset is None or asset.access_token != token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uploaded asset not found.")

    file_path = Path(asset.stored_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uploaded file is missing.")

    return FileResponse(file_path, media_type=asset.mime_type, filename=asset.original_filename)
