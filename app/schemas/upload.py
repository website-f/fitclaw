from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.uploaded_asset import UploadedAssetKind


class UploadedAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    kind: UploadedAssetKind
    original_filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime
    public_url: str
