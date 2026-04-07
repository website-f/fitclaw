from __future__ import annotations

import mimetypes
from pathlib import Path
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.uploaded_asset import UploadedAsset, UploadedAssetKind

settings = get_settings()

UPLOAD_DIR = Path("/data/uploads")


class UploadService:
    @staticmethod
    def create_asset_from_bytes(
        db: Session,
        platform_user_id: str,
        session_id: str | None,
        source: str,
        original_filename: str,
        mime_type: str | None,
        raw_bytes: bytes,
        kind: UploadedAssetKind | None = None,
        metadata_json: dict | None = None,
    ) -> UploadedAsset:
        if not raw_bytes:
            raise ValueError("Uploaded file is empty.")
        if len(raw_bytes) > settings.upload_max_bytes:
            raise ValueError(f"Uploaded file exceeds the maximum size of {settings.upload_max_bytes} bytes.")

        inferred_mime = (mime_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream").strip()
        asset_kind = kind or UploadService._detect_kind(original_filename, inferred_mime)
        asset_id = f"ast_{secrets.token_hex(12)}"
        access_token = secrets.token_urlsafe(18)
        extension = UploadService._guess_extension(original_filename, inferred_mime)
        user_dir = UPLOAD_DIR / platform_user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        stored_path = user_dir / f"{asset_id}{extension}"
        stored_path.write_bytes(raw_bytes)

        asset = UploadedAsset(
            asset_id=asset_id,
            access_token=access_token,
            platform_user_id=platform_user_id,
            session_id=session_id,
            source=source,
            kind=asset_kind,
            original_filename=original_filename or stored_path.name,
            stored_path=str(stored_path),
            mime_type=inferred_mime,
            size_bytes=len(raw_bytes),
            metadata_json=metadata_json or {},
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset

    @staticmethod
    def get_asset(db: Session, asset_id: str) -> UploadedAsset | None:
        return db.scalar(select(UploadedAsset).where(UploadedAsset.asset_id == asset_id))

    @staticmethod
    def get_assets_for_user(db: Session, asset_ids: list[str], platform_user_id: str) -> list[UploadedAsset]:
        if not asset_ids:
            return []
        records = list(
            db.scalars(
                select(UploadedAsset)
                .where(UploadedAsset.asset_id.in_(asset_ids))
                .where(UploadedAsset.platform_user_id == platform_user_id)
            ).all()
        )
        records.sort(key=lambda item: asset_ids.index(item.asset_id))
        return records

    @staticmethod
    def build_public_url(asset: UploadedAsset) -> str:
        return f"/api/v1/uploads/{asset.asset_id}?token={asset.access_token}"

    @staticmethod
    def load_bytes(asset: UploadedAsset) -> bytes:
        return Path(asset.stored_path).read_bytes()

    @staticmethod
    def create_generated_image_asset(
        db: Session,
        platform_user_id: str,
        session_id: str | None,
        original_filename: str,
        image_bytes: bytes,
        metadata_json: dict | None = None,
    ) -> UploadedAsset:
        return UploadService.create_asset_from_bytes(
            db=db,
            platform_user_id=platform_user_id,
            session_id=session_id,
            source="generated",
            original_filename=original_filename,
            mime_type="image/png",
            raw_bytes=image_bytes,
            kind=UploadedAssetKind.image,
            metadata_json=metadata_json,
        )

    @staticmethod
    def _detect_kind(filename: str, mime_type: str) -> UploadedAssetKind:
        if mime_type.startswith("image/"):
            return UploadedAssetKind.image
        extension = Path(filename).suffix.lower()
        if extension in {".txt", ".md", ".py", ".json", ".csv", ".log", ".yaml", ".yml", ".xml", ".html", ".js", ".ts", ".tsx", ".jsx", ".pdf"}:
            return UploadedAssetKind.document
        return UploadedAssetKind.binary

    @staticmethod
    def _guess_extension(filename: str, mime_type: str) -> str:
        suffix = Path(filename).suffix
        if suffix:
            return suffix
        guessed = mimetypes.guess_extension(mime_type)
        return guessed or ".bin"
