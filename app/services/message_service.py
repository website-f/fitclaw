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
from app.services.finance_service import FinanceService
from app.services.llm_service import LLMService, LLMServiceError
from app.services.memory_service import MemoryService
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
    def _build_system_prompt(
        db: Session,
        user_id: str,
        session_id: str | None = None,
        user_text: str | None = None,
    ) -> str:
        prompt = settings.system_prompt
        kb_context = MessageService._build_knowledge_context(db, user_id=user_id, user_text=user_text)
        if kb_context:
            prompt = f"{prompt}\n\n{kb_context}"
        return prompt

    @staticmethod
    def _build_knowledge_context(
        db: Session,
        *,
        user_id: str,
        user_text: str | None,
    ) -> str:
        if not user_text:
            return ""
        cleaned = user_text.strip()
        # Skip retrieval for trivially short messages so we don't pollute the prompt.
        if len(cleaned) < 12:
            return ""
        try:
            from app.modules.knowledge.service import KnowledgeService
            hits = KnowledgeService.search(db, user_id=user_id, query=cleaned, limit=3)
        except Exception:
            return ""
        if not hits:
            return ""
        blocks = ["Knowledge base excerpts (cite via [KB:doc-id#chunk] when relevant):"]
        for hit in hits:
            blocks.append(f"[KB:{hit.doc_id}#{hit.chunk_index}] ({hit.title})\n{hit.text.strip()}")
        return "\n\n".join(blocks)

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

        handoff_reply = MessageService._maybe_open_handoff(
            db,
            user_id=user_id,
            session_id=resolved_session_id,
            text=normalized_text,
        )
        if handoff_reply is not None:
            MessageService._store_assistant_message(
                db=db,
                session_id=resolved_session_id,
                user_id=user_id,
                content=handoff_reply,
                username=username,
                provider="handoff",
            )
            return ProcessedMessage(
                reply=handoff_reply,
                provider="handoff",
                session_id=resolved_session_id,
                handled_as_task_command=False,
                handled_as_agent_command=False,
                attachments=[],
            )

        command_result = None
        if assets:
            history = MemoryService.get_recent_messages(db, resolved_session_id, limit=settings.memory_window)
            prompt_messages = [{"role": "system", "content": MessageService._build_system_prompt(db, user_id, resolved_session_id, user_text=normalized_text)}] + MemoryService.to_llm_messages(history)
            active_llm = RuntimeConfigService.get_active_llm(db)
            command_result = FinanceService.try_handle(
                db=db,
                user_id=user_id,
                session_id=resolved_session_id,
                text=normalized_text,
                assets=assets,
                prompt_messages=prompt_messages,
                active_provider=active_llm["provider"],
                active_model=active_llm["model"],
            )
        if command_result is None and assets:
            history = MemoryService.get_recent_messages(db, resolved_session_id, limit=settings.memory_window)
            prompt_messages = [{"role": "system", "content": MessageService._build_system_prompt(db, user_id, resolved_session_id, user_text=normalized_text)}] + MemoryService.to_llm_messages(history)
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
            command_result = FinanceService.try_handle(
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
            prompt_messages = [{"role": "system", "content": MessageService._build_system_prompt(db, user_id, resolved_session_id, user_text=normalized_text)}] + MemoryService.to_llm_messages(history)
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
        prompt_messages = [{"role": "system", "content": MessageService._build_system_prompt(db, user_id, resolved_session_id, user_text=normalized_text)}] + MemoryService.to_llm_messages(history)
        active_llm = RuntimeConfigService.get_active_llm(db)
        try:
            reply, provider = LLMService.generate_reply(
                prompt_messages,
                active_provider=active_llm["provider"],
                active_model=active_llm["model"],
            )
        except LLMServiceError as exc:
            _ = exc
            reply = (
                "I couldn't reach the configured language model right now. "
                "Please try again in a minute. Agent and task commands can still work while the chat model is unavailable."
            )
            provider = "llm-error"
        except Exception as exc:
            _ = exc
            reply = (
                "I hit an unexpected chat-processing error before I could answer. "
                "Please try again in a moment. Task commands and agent actions are still available while I recover."
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

        MessageService._log_chat_audit(
            db,
            user_id=user_id,
            session_id=resolved_session_id,
            provider=provider,
            user_text=normalized_text,
            reply=reply,
        )

        return ProcessedMessage(
            reply=reply,
            provider=provider,
            session_id=resolved_session_id,
            handled_as_task_command=False,
            handled_as_agent_command=False,
            attachments=[],
        )

    @staticmethod
    def _maybe_open_handoff(
        db: Session,
        *,
        user_id: str,
        session_id: str,
        text: str,
    ) -> str | None:
        cleaned = (text or "").strip()
        if not cleaned:
            return None
        try:
            from app.modules.governance.service import HandoffService
        except Exception:
            return None
        if not HandoffService.should_handoff(cleaned):
            return None
        try:
            row = HandoffService.open(
                db,
                user_id=user_id,
                question=cleaned,
                session_id=session_id,
                reason="keyword",
            )
        except Exception:
            return None
        return (
            "I'm escalating this to a human teammate.\n"
            f"Handoff id: `{row.handoff_id}`. You'll see their reply right here in this chat once they respond."
        )

    @staticmethod
    def _log_chat_audit(
        db: Session,
        *,
        user_id: str,
        session_id: str,
        provider: str | None,
        user_text: str,
        reply: str,
    ) -> None:
        try:
            from app.modules.audit.service import AuditService
            AuditService.log(
                db,
                user_id=user_id,
                source="chat",
                action="chat.reply",
                summary=(user_text or "")[:240] or "(empty)",
                actor=provider,
                detail={
                    "session_id": session_id,
                    "provider": provider,
                    "reply_chars": len(reply or ""),
                },
            )
        except Exception:
            return
