from enum import Enum

from sqlalchemy import JSON, BigInteger, DateTime, Enum as SqlEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class UploadedAssetKind(str, Enum):
    image = "image"
    document = "document"
    binary = "binary"


class UploadedAsset(Base):
    __tablename__ = "uploaded_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    access_token: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    platform_user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="upload", nullable=False)
    kind: Mapped[UploadedAssetKind] = mapped_column(SqlEnum(UploadedAssetKind), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
