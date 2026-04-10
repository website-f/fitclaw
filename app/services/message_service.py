from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.conversation import MessageRole
from app.services.agent_automation_service import AgentAutomationService
from app.services.agent_command_service import AgentCommandService
from app.services.attachment_service import AttachmentService
from app.services.calendar_service import CalendarService
from app.services.command_service import TaskCommandService
from app.services.command_result import MessageAttachment
from app.services.llm_service import LLMService, LLMServiceError
from app.services.memory_service import MemoryService
from app.services.memorycore_service import MemoryCoreService
from app.services.runtime_config_service import RuntimeConfigService
from app.services.transit_service import TransitService
from app.services.upload_service import UploadService
from app.services.weather_service import WeatherService
from app.services.web_content_service import WebContentService

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
    def _build_system_prompt(db: Session, user_id: str, session_id: str | None = None) -> str:
        linked_project_key = None
        if session_id:
            linked_project_key = MemoryCoreService.get_linked_project_key(db, user_id=user_id, session_id=session_id)
        memory_context = MemoryCoreService.build_assistant_context(
            db,
            user_id=user_id,
            project_key=linked_project_key,
        )
        if not memory_context:
            return settings.system_prompt
        return f"{settings.system_prompt}\n\nMemoryCore context:\n{memory_context}"

    @staticmethod
    def _sync_memorycore_session_context(db: Session, user_id: str, session_id: str) -> None:
        project_key = MemoryCoreService.get_linked_project_key(db, user_id=user_id, session_id=session_id)
        if not project_key:
            return
        try:
            MemoryCoreService.capture_session_context(
                db,
                user_id=user_id,
                project_key=project_key,
                session_id=session_id,
            )
        except Exception:
            return

    @staticmethod
    def _store_assistant_message(
        db: Session,
        *,
        user_id: str,
        session_id: str,
        content: str,
        username: str | None = None,
        provider: str | None = None,
        metadata_json: dict | None = None,
    ) -> None:
        MemoryService.add_message(
            db=db,
            session_id=session_id,
            platform_user_id=user_id,
            role=MessageRole.assistant,
            content=content,
            username=username,
            provider=provider,
            metadata_json=metadata_json,
        )
        MessageService._sync_memorycore_session_context(db, user_id=user_id, session_id=session_id)

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
        resolved_asset_ids = list(attachment_asset_ids or [])
        if not resolved_asset_ids and AttachmentService.should_use_recent_assets(normalized_text):
            resolved_asset_ids = MemoryService.get_recent_attachment_asset_ids(
                db=db,
                session_id=resolved_session_id,
                platform_user_id=user_id,
            )

        assets = UploadService.get_assets_for_user(db, resolved_asset_ids, user_id)
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

        command_result = None
        if assets:
            history = MemoryService.get_recent_messages(db, resolved_session_id, limit=settings.memory_window)
            prompt_messages = [{"role": "system", "content": MessageService._build_system_prompt(db, user_id, resolved_session_id)}] + MemoryService.to_llm_messages(history)
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
        if command_result is None:
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
        if command_result is None:
            command_result = AgentAutomationService.try_handle(
                db=db,
                user_id=user_id,
                session_id=resolved_session_id,
                text=normalized_text,
            )
        if command_result is None:
            command_result = CalendarService.try_handle(
                db=db,
                user_id=user_id,
                session_id=resolved_session_id,
                text=normalized_text,
            )
        if command_result is None:
            command_result = WeatherService.try_handle(normalized_text)
        if command_result is None:
            command_result = TransitService.try_handle(normalized_text)
        if command_result is None:
            history = MemoryService.get_recent_messages(db, resolved_session_id, limit=settings.memory_window)
            prompt_messages = [{"role": "system", "content": MessageService._build_system_prompt(db, user_id, resolved_session_id)}] + MemoryService.to_llm_messages(history)
            active_llm = RuntimeConfigService.get_active_llm(db)
            command_result = WebContentService.try_handle(
                text=normalized_text,
                prompt_messages=prompt_messages,
                active_provider=active_llm["provider"],
                active_model=active_llm["model"],
            )
        if command_result is not None:
            metadata_json = dict(command_result.metadata_json or {})
            if command_result.attachments:
                metadata_json["attachments"] = [attachment.to_metadata() for attachment in command_result.attachments]
            MessageService._store_assistant_message(
                db=db,
                session_id=resolved_session_id,
                user_id=user_id,
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
        prompt_messages = [{"role": "system", "content": MessageService._build_system_prompt(db, user_id, resolved_session_id)}] + MemoryService.to_llm_messages(history)
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

        MessageService._store_assistant_message(
            db=db,
            session_id=resolved_session_id,
            user_id=user_id,
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
