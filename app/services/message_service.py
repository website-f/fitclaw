from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.conversation import MessageRole
from app.services.agent_command_service import AgentCommandService
from app.services.attachment_service import AttachmentService
from app.services.command_service import TaskCommandService
from app.services.command_result import MessageAttachment
from app.services.llm_service import LLMService, LLMServiceError
from app.services.memory_service import MemoryService
from app.services.runtime_config_service import RuntimeConfigService
from app.services.upload_service import UploadService

settings = get_settings()


@dataclass
class ProcessedMessage:
    reply: str
    provider: str
    session_id: str
    handled_as_task_command: bool
    handled_as_agent_command: bool
    attachments: list[MessageAttachment]


class MessageService:
    @staticmethod
    def process_user_message(
        db: Session,
        user_id: str,
        text: str,
        username: str | None = None,
        session_id: str | None = None,
        attachment_asset_ids: list[str] | None = None,
    ) -> ProcessedMessage:
        resolved_session_id = session_id or f"telegram:{user_id}"
        normalized_text = text.strip()
        assets = UploadService.get_assets_for_user(db, attachment_asset_ids or [], user_id)
        user_metadata = {}
        if assets:
            user_metadata["attachments"] = AttachmentService.build_metadata(assets)

        MemoryService.add_message(
            db=db,
            session_id=resolved_session_id,
            platform_user_id=user_id,
            role=MessageRole.user,
            content=normalized_text,
            username=username,
            metadata_json=user_metadata,
        )

        command_result = TaskCommandService.try_handle(
            db=db,
            user_id=user_id,
            session_id=resolved_session_id,
            text=normalized_text,
        )
        if command_result is None:
            command_result = AgentCommandService.try_handle(
                db=db,
                user_id=user_id,
                text=normalized_text,
            )
        if command_result is None and assets:
            history = MemoryService.get_recent_messages(db, resolved_session_id, limit=settings.memory_window)
            prompt_messages = [{"role": "system", "content": settings.system_prompt}] + MemoryService.to_llm_messages(history)
            active_llm = RuntimeConfigService.get_active_llm(db)
            command_result = AttachmentService.try_handle(
                db=db,
                user_id=user_id,
                session_id=resolved_session_id,
                text=normalized_text,
                assets=assets,
                prompt_messages=prompt_messages,
                active_provider=active_llm["provider"],
                active_model=active_llm["model"],
            )
        if command_result is not None:
            metadata_json = {}
            if command_result.attachments:
                metadata_json["attachments"] = [attachment.to_metadata() for attachment in command_result.attachments]
            MemoryService.add_message(
                db=db,
                session_id=resolved_session_id,
                platform_user_id=user_id,
                role=MessageRole.assistant,
                content=command_result.reply,
                username=username,
                provider=command_result.provider,
                metadata_json=metadata_json,
            )
            return ProcessedMessage(
                reply=command_result.reply,
                provider=command_result.provider,
                session_id=resolved_session_id,
                handled_as_task_command=command_result.handled_as_task_command,
                handled_as_agent_command=command_result.handled_as_agent_command,
                attachments=command_result.attachments,
            )

        history = MemoryService.get_recent_messages(db, resolved_session_id, limit=settings.memory_window)
        prompt_messages = [{"role": "system", "content": settings.system_prompt}] + MemoryService.to_llm_messages(history)
        active_llm = RuntimeConfigService.get_active_llm(db)
        try:
            reply, provider = LLMService.generate_reply(
                prompt_messages,
                active_provider=active_llm["provider"],
                active_model=active_llm["model"],
            )
        except LLMServiceError as exc:
            reply = (
                "I couldn't reach the configured language model right now.\n\n"
                f"{exc}\n\n"
                "Agent and task commands can still work while the chat model is unavailable."
            )
            provider = "llm-error"
        except Exception as exc:
            reply = (
                "I hit an unexpected chat-processing error before I could answer.\n\n"
                f"{exc}\n\n"
                "Task commands and agent actions are still available while I recover."
            )
            provider = "llm-error"

        MemoryService.add_message(
            db=db,
            session_id=resolved_session_id,
            platform_user_id=user_id,
            role=MessageRole.assistant,
            content=reply,
            username=username,
            provider=provider,
        )

        return ProcessedMessage(
            reply=reply,
            provider=provider,
            session_id=resolved_session_id,
            handled_as_task_command=False,
            handled_as_agent_command=False,
            attachments=[],
        )
