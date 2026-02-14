from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from insightxpert.auth.models import ConversationRecord, MessageRecord

logger = logging.getLogger("insightxpert.auth")


class PersistentConversationStore:
    def __init__(self, engine):
        self.engine = engine

    def get_conversations(self, user_id: str) -> list[dict]:
        with Session(self.engine) as session:
            # Subquery: latest message created_at per conversation
            latest_msg = (
                select(
                    MessageRecord.conversation_id,
                    func.max(MessageRecord.created_at).label("max_created"),
                )
                .group_by(MessageRecord.conversation_id)
                .subquery()
            )

            rows = (
                session.query(
                    ConversationRecord,
                    MessageRecord.content.label("last_content"),
                )
                .outerjoin(
                    latest_msg,
                    ConversationRecord.id == latest_msg.c.conversation_id,
                )
                .outerjoin(
                    MessageRecord,
                    (MessageRecord.conversation_id == latest_msg.c.conversation_id)
                    & (MessageRecord.created_at == latest_msg.c.max_created),
                )
                .filter(ConversationRecord.user_id == user_id)
                .order_by(desc(ConversationRecord.updated_at))
                .all()
            )

            return [
                {
                    "id": c.id,
                    "title": c.title,
                    "created_at": c.created_at.isoformat(),
                    "updated_at": c.updated_at.isoformat(),
                    "last_message": last_content[:200] if last_content else None,
                }
                for c, last_content in rows
            ]

    def get_conversation(self, conversation_id: str, user_id: str) -> dict | None:
        with Session(self.engine) as session:
            convo = session.get(ConversationRecord, conversation_id)
            if convo is None or convo.user_id != user_id:
                return None

            messages = (
                session.query(MessageRecord)
                .filter(MessageRecord.conversation_id == conversation_id)
                .order_by(MessageRecord.created_at)
                .all()
            )
            return {
                "id": convo.id,
                "title": convo.title,
                "created_at": convo.created_at.isoformat(),
                "updated_at": convo.updated_at.isoformat(),
                "messages": [
                    {
                        "id": m.id,
                        "role": m.role,
                        "content": m.content,
                        "chunks_json": m.chunks_json,
                        "created_at": m.created_at.isoformat(),
                    }
                    for m in messages
                ],
            }

    def get_or_create_conversation(self, conversation_id: str, user_id: str, title: str) -> dict:
        with Session(self.engine) as session:
            convo = session.get(ConversationRecord, conversation_id)
            if convo is not None:
                if convo.user_id == user_id:
                    return {
                        "id": convo.id,
                        "title": convo.title,
                        "created_at": convo.created_at.isoformat(),
                        "updated_at": convo.updated_at.isoformat(),
                    }
                raise ValueError("Conversation not owned by user")

            now = datetime.now(timezone.utc)
            convo = ConversationRecord(
                id=conversation_id,
                user_id=user_id,
                title=title,
                created_at=now,
                updated_at=now,
            )
            session.add(convo)
            session.commit()
            return {
                "id": convo.id,
                "title": convo.title,
                "created_at": convo.created_at.isoformat(),
                "updated_at": convo.updated_at.isoformat(),
            }

    def create_conversation(self, user_id: str, title: str) -> dict:
        now = datetime.now(timezone.utc)
        convo = ConversationRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
        )
        with Session(self.engine) as session:
            session.add(convo)
            session.commit()
            return {
                "id": convo.id,
                "title": convo.title,
                "created_at": convo.created_at.isoformat(),
                "updated_at": convo.updated_at.isoformat(),
            }

    def save_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        chunks_json: str | None = None,
    ) -> str:
        with Session(self.engine) as session:
            convo = session.get(ConversationRecord, conversation_id)
            if convo is None or convo.user_id != user_id:
                raise ValueError("Conversation not found or not owned by user")

            msg = MessageRecord(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                role=role,
                content=content,
                chunks_json=chunks_json,
                created_at=datetime.now(timezone.utc),
            )
            convo.updated_at = datetime.now(timezone.utc)
            session.add(msg)
            session.commit()
            return msg.id

    def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        with Session(self.engine) as session:
            convo = session.get(ConversationRecord, conversation_id)
            if convo is None or convo.user_id != user_id:
                return False
            # Delete messages first (cascade may handle this, but be explicit)
            session.query(MessageRecord).filter(
                MessageRecord.conversation_id == conversation_id
            ).delete()
            session.delete(convo)
            session.commit()
            return True

    def rename_conversation(self, conversation_id: str, user_id: str, title: str) -> bool:
        with Session(self.engine) as session:
            convo = session.get(ConversationRecord, conversation_id)
            if convo is None or convo.user_id != user_id:
                return False
            convo.title = title
            convo.updated_at = datetime.now(timezone.utc)
            session.commit()
            return True
