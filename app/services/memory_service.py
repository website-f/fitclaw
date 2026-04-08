from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.orm import Session

from app.models.conversation import ConversationMessage, MessageRole


class MemoryService:
    @staticmethod
    def add_message(
        db: Session,
        session_id: str,
        platform_user_id: str,
        role: MessageRole,
        content: str,
        username: str | None = None,
        provider: str | None = None,
        metadata_json: dict | None = None,
    ) -> ConversationMessage:
        message = ConversationMessage(
            session_id=session_id,
            platform_user_id=platform_user_id,
            username=username,
            role=role,
            content=content,
            provider=provider,
            metadata_json=metadata_json or {},
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message

    @staticmethod
    def get_recent_messages(db: Session, session_id: str, limit: int = 12) -> list[ConversationMessage]:
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        return list(reversed(list(db.scalars(stmt).all())))

    @staticmethod
    def list_session_messages(
        db: Session,
        session_id: str,
        platform_user_id: str | None = None,
        limit: int = 200,
    ) -> list[ConversationMessage]:
        stmt = select(ConversationMessage).where(ConversationMessage.session_id == session_id)
        if platform_user_id is not None:
            stmt = stmt.where(ConversationMessage.platform_user_id == platform_user_id)
        stmt = stmt.order_by(ConversationMessage.created_at.asc()).limit(limit)
        return list(db.scalars(stmt).all())

    @staticmethod
    def list_sessions(db: Session, platform_user_id: str, limit: int = 24) -> list[dict]:
        session_rows = db.execute(
            select(
                ConversationMessage.session_id,
                func.max(ConversationMessage.created_at).label("last_message_at"),
                func.count(ConversationMessage.id).label("message_count"),
            )
            .where(ConversationMessage.platform_user_id == platform_user_id)
            .group_by(ConversationMessage.session_id)
            .order_by(func.max(ConversationMessage.created_at).desc())
            .limit(limit)
        ).all()

        session_ids = [str(row.session_id) for row in session_rows]
        latest_by_session: dict[str, ConversationMessage] = {}
        first_user_by_session: dict[str, ConversationMessage] = {}

        if session_ids:
            latest_messages = db.scalars(
                select(ConversationMessage)
                .where(ConversationMessage.platform_user_id == platform_user_id)
                .where(ConversationMessage.session_id.in_(session_ids))
                .order_by(
                    ConversationMessage.session_id.asc(),
                    ConversationMessage.created_at.desc(),
                    ConversationMessage.id.desc(),
                )
            ).all()
            for message in latest_messages:
                latest_by_session.setdefault(str(message.session_id), message)

            first_user_messages = db.scalars(
                select(ConversationMessage)
                .where(ConversationMessage.platform_user_id == platform_user_id)
                .where(ConversationMessage.session_id.in_(session_ids))
                .where(ConversationMessage.role == MessageRole.user)
                .order_by(
                    ConversationMessage.session_id.asc(),
                    ConversationMessage.created_at.asc(),
                    ConversationMessage.id.asc(),
                )
            ).all()
            for message in first_user_messages:
                first_user_by_session.setdefault(str(message.session_id), message)

        summaries: list[dict] = []
        for row in session_rows:
            session_id = str(row.session_id)
            latest = latest_by_session.get(session_id)
            first_user = first_user_by_session.get(session_id)

            title_source = (first_user.content if first_user else latest.content if latest else session_id).strip()
            title = title_source.replace("\n", " ")
            preview_source = (latest.content if latest else "").strip().replace("\n", " ")
            summaries.append(
                {
                    "session_id": session_id,
                    "title": title[:80] or "New chat",
                    "preview": preview_source[:140],
                    "last_message_at": row.last_message_at,
                    "message_count": int(row.message_count),
                    "last_role": latest.role.value if latest else MessageRole.assistant.value,
                }
            )

        return summaries

    @staticmethod
    def delete_session(db: Session, session_id: str, platform_user_id: str) -> int:
        result = db.execute(
            sa_delete(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .where(ConversationMessage.platform_user_id == platform_user_id)
        )
        db.commit()
        return result.rowcount  # type: ignore[return-value]

    @staticmethod
    def delete_all_sessions(db: Session, platform_user_id: str) -> int:
        result = db.execute(
            sa_delete(ConversationMessage)
            .where(ConversationMessage.platform_user_id == platform_user_id)
        )
        db.commit()
        return result.rowcount  # type: ignore[return-value]

    @staticmethod
    def get_recent_attachment_asset_ids(
        db: Session,
        session_id: str,
        platform_user_id: str,
        limit: int = 12,
    ) -> list[str]:
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .where(ConversationMessage.platform_user_id == platform_user_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )

        seen: set[str] = set()
        results: list[str] = []
        for message in db.scalars(stmt).all():
            attachments = list((message.metadata_json or {}).get("attachments", []))
            current_ids = []
            for item in attachments:
                if not isinstance(item, dict):
                    continue
                asset_id = str(item.get("asset_id", "")).strip()
                if asset_id and asset_id not in seen:
                    current_ids.append(asset_id)
                    seen.add(asset_id)
            if current_ids:
                results.extend(current_ids)
                break

        return results

    @staticmethod
    def to_llm_messages(messages: list[ConversationMessage]) -> list[dict[str, str]]:
        return [{"role": item.role.value, "content": item.content} for item in messages]
