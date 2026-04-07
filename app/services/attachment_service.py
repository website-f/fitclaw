from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
import re

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.uploaded_asset import UploadedAsset, UploadedAssetKind
from app.services.command_result import CommandResult, MessageAttachment
from app.services.llm_service import LLMService
from app.services.upload_service import UploadService

settings = get_settings()


class AttachmentService:
    TEXT_EXTENSIONS = {
        ".txt",
        ".md",
        ".py",
        ".json",
        ".csv",
        ".log",
        ".yaml",
        ".yml",
        ".xml",
        ".html",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".ini",
        ".toml",
        ".sql",
    }

    @staticmethod
    def build_message_attachments(assets: list[UploadedAsset]) -> list[MessageAttachment]:
        attachments: list[MessageAttachment] = []
        for asset in assets:
            attachments.append(
                MessageAttachment(
                    kind="photo" if asset.kind == UploadedAssetKind.image else "document",
                    path=asset.stored_path,
                    filename=asset.original_filename,
                    explicit_public_url=UploadService.build_public_url(asset),
                )
            )
        return attachments

    @staticmethod
    def build_metadata(assets: list[UploadedAsset]) -> list[dict]:
        return [
            {
                "asset_id": asset.asset_id,
                "kind": asset.kind.value,
                "filename": asset.original_filename,
                "mime_type": asset.mime_type,
                "size_bytes": asset.size_bytes,
                "public_url": UploadService.build_public_url(asset),
            }
            for asset in assets
        ]

    @staticmethod
    def try_handle(
        db: Session,
        user_id: str,
        session_id: str,
        text: str,
        assets: list[UploadedAsset],
        prompt_messages: list[dict[str, str]],
        active_provider: str,
        active_model: str,
    ) -> CommandResult | None:
        if not assets:
            return None

        normalized_text = text.strip()
        image_assets = [asset for asset in assets if asset.kind == UploadedAssetKind.image]
        document_assets = [asset for asset in assets if asset.kind != UploadedAssetKind.image]

        if image_assets and AttachmentService._looks_like_edit_request(normalized_text):
            return AttachmentService._handle_image_edit(db, user_id, session_id, normalized_text, image_assets[0])

        if image_assets:
            return AttachmentService._handle_image_analysis(
                normalized_text=normalized_text,
                image_assets=image_assets,
                prompt_messages=prompt_messages,
                active_provider=active_provider,
                active_model=active_model,
            )

        if document_assets:
            return AttachmentService._handle_document_analysis(
                normalized_text=normalized_text,
                document_assets=document_assets,
                prompt_messages=prompt_messages,
                active_provider=active_provider,
                active_model=active_model,
            )

        return None

    @staticmethod
    def _handle_document_analysis(
        normalized_text: str,
        document_assets: list[UploadedAsset],
        prompt_messages: list[dict[str, str]],
        active_provider: str,
        active_model: str,
    ) -> CommandResult:
        extracted_parts: list[str] = []
        for asset in document_assets[:4]:
            content = AttachmentService.extract_text(asset)
            extracted_parts.append(
                f"Attachment: {asset.original_filename}\n"
                f"MIME: {asset.mime_type}\n"
                f"Content excerpt:\n{content}"
            )

        request_text = normalized_text or "Summarize the uploaded file and highlight any important actions or risks."
        augmented_messages = list(prompt_messages)
        augmented_messages[-1] = {
            "role": "user",
            "content": f"{request_text}\n\nUploaded file context:\n\n" + "\n\n---\n\n".join(extracted_parts),
        }

        try:
            reply, provider = LLMService.generate_reply(
                augmented_messages,
                active_provider=active_provider,
                active_model=active_model,
            )
        except Exception as exc:
            return CommandResult(
                reply=f"I could not analyze the uploaded file right now.\n\n{exc}",
                provider="attachment-error",
            )

        return CommandResult(
            reply=reply,
            provider=provider,
            attachments=AttachmentService.build_message_attachments(document_assets),
        )

    @staticmethod
    def _handle_image_analysis(
        normalized_text: str,
        image_assets: list[UploadedAsset],
        prompt_messages: list[dict[str, str]],
        active_provider: str,
        active_model: str,
    ) -> CommandResult:
        request_text = normalized_text or "Describe this image clearly and extract any important text or visual details."

        try:
            reply, provider = LLMService.generate_vision_reply(
                prompt_messages=prompt_messages,
                prompt_text=request_text,
                image_assets=image_assets,
                active_provider=active_provider,
                active_model=active_model,
            )
        except Exception as exc:
            return CommandResult(
                reply=f"I could not analyze the uploaded image right now.\n\n{exc}",
                provider="attachment-error",
                attachments=AttachmentService.build_message_attachments(image_assets),
            )

        return CommandResult(
            reply=reply,
            provider=provider,
            attachments=AttachmentService.build_message_attachments(image_assets),
        )

    @staticmethod
    def _handle_image_edit(
        db: Session,
        user_id: str,
        session_id: str,
        normalized_text: str,
        image_asset: UploadedAsset,
    ) -> CommandResult:
        image = Image.open(BytesIO(UploadService.load_bytes(image_asset))).convert("RGBA")
        operations: list[str] = []
        text_lower = normalized_text.lower()

        if "grayscale" in text_lower or "black and white" in text_lower:
            image = ImageOps.grayscale(image).convert("RGBA")
            operations.append("grayscale")
        if "invert" in text_lower:
            rgb = image.convert("RGB")
            image = ImageOps.invert(rgb).convert("RGBA")
            operations.append("invert")
        if "blur" in text_lower:
            image = image.filter(ImageFilter.GaussianBlur(radius=2.2))
            operations.append("blur")
        if "sharpen" in text_lower:
            image = image.filter(ImageFilter.SHARPEN)
            operations.append("sharpen")
        if "flip horizontal" in text_lower or "mirror" in text_lower:
            image = ImageOps.mirror(image)
            operations.append("flip horizontal")
        if "flip vertical" in text_lower:
            image = ImageOps.flip(image)
            operations.append("flip vertical")
        if "rotate left" in text_lower:
            image = image.rotate(90, expand=True)
            operations.append("rotate left")
        if "rotate right" in text_lower:
            image = image.rotate(-90, expand=True)
            operations.append("rotate right")
        if "rotate 180" in text_lower:
            image = image.rotate(180, expand=True)
            operations.append("rotate 180")

        size_match = re.search(r"(\d{2,5})\s*[xX]\s*(\d{2,5})", normalized_text)
        if size_match:
            width = max(1, int(size_match.group(1)))
            height = max(1, int(size_match.group(2)))
            image = image.resize((width, height))
            operations.append(f"resize {width}x{height}")

        bright_match = re.search(r"bright(?:en|ness)?\s+(\d+)%", text_lower)
        if bright_match:
            factor = max(int(bright_match.group(1)), 1) / 100
            image = ImageEnhance.Brightness(image).enhance(factor)
            operations.append(f"brightness {bright_match.group(1)}%")

        contrast_match = re.search(r"contrast\s+(\d+)%", text_lower)
        if contrast_match:
            factor = max(int(contrast_match.group(1)), 1) / 100
            image = ImageEnhance.Contrast(image).enhance(factor)
            operations.append(f"contrast {contrast_match.group(1)}%")

        if not operations:
            return CommandResult(
                reply=(
                    "I can edit images with operations like `grayscale`, `blur`, `sharpen`, "
                    "`rotate left`, `flip horizontal`, or `resize 1024x1024`."
                ),
                provider="attachment-edit",
                attachments=AttachmentService.build_message_attachments([image_asset]),
            )

        output = BytesIO()
        image.save(output, format="PNG")
        output.seek(0)
        generated = UploadService.create_generated_image_asset(
            db=db,
            platform_user_id=user_id,
            session_id=session_id,
            original_filename=f"edited-{Path(image_asset.original_filename).stem}.png",
            image_bytes=output.getvalue(),
            metadata_json={"source_asset_id": image_asset.asset_id, "operations": operations},
        )

        return CommandResult(
            reply=f"Edited image ready. Applied: {', '.join(operations)}.",
            provider="attachment-edit",
            attachments=AttachmentService.build_message_attachments([generated]),
        )

    @staticmethod
    def extract_text(asset: UploadedAsset) -> str:
        suffix = Path(asset.original_filename).suffix.lower()
        raw = UploadService.load_bytes(asset)

        if suffix == ".pdf":
            reader = PdfReader(BytesIO(raw))
            parts = []
            for page in reader.pages[:20]:
                parts.append(page.extract_text() or "")
            text = "\n".join(parts)
        else:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("utf-8", errors="replace")

        text = text.strip()
        if not text:
            text = "(No readable text content found.)"
        return text[: settings.upload_extract_text_chars]

    @staticmethod
    def encode_image_asset(asset: UploadedAsset) -> tuple[str, str]:
        raw = UploadService.load_bytes(asset)
        return base64.b64encode(raw).decode("ascii"), asset.mime_type

    @staticmethod
    def _looks_like_edit_request(text: str) -> bool:
        lowered = text.lower()
        return any(
            token in lowered
            for token in (
                "edit",
                "grayscale",
                "black and white",
                "blur",
                "sharpen",
                "rotate",
                "flip",
                "resize",
                "contrast",
                "brightness",
                "invert",
                "crop",
            )
        )
