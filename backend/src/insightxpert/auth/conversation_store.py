from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import true as sa_true

from insightxpert.auth.models import ConversationRecord, MessageRecord, _record_delete

logger = logging.getLogger("insightxpert.auth")

IST = ZoneInfo("Asia/Kolkata")


def _to_ist(dt: datetime) -> str:
    """Convert a UTC datetime to IST and return as ISO string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).isoformat()


def _conv_to_dict(convo: ConversationRecord) -> dict:
    return {
        "id": convo.id,
        "org_id": convo.org_id,
        "title": convo.title,
        "is_starred": convo.is_starred,
        "created_at": _to_ist(convo.created_at),
        "updated_at": _to_ist(convo.updated_at),
    }


class PersistentConversationStore:
    def __init__(self, engine):
        self.engine = engine

    def get_conversations(self, user_id: str, org_id: str | None = None) -> list[dict]:
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

            q = (
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
            )

            if org_id is not None:
                q = q.filter(ConversationRecord.org_id == org_id)

            rows = q.order_by(desc(ConversationRecord.updated_at)).all()

            return [
                {**_conv_to_dict(c), "last_message": last_content[:200] if last_content else None}
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
                **_conv_to_dict(convo),
                "messages": [
                    {
                        "id": m.id,
                        "role": m.role,
                        "content": m.content,
                        "chunks_json": m.chunks_json,
                        "feedback": m.feedback,
                        "feedback_comment": m.feedback_comment,
                        "input_tokens": m.input_tokens,
                        "output_tokens": m.output_tokens,
                        "generation_time_ms": m.generation_time_ms,
                        "created_at": _to_ist(m.created_at),
                    }
                    for m in messages
                ],
            }

    def get_or_create_conversation(self, conversation_id: str, user_id: str, title: str, org_id: str | None = None) -> dict:
        with Session(self.engine) as session:
            convo = session.get(ConversationRecord, conversation_id)
            if convo is not None:
                if convo.user_id == user_id:
                    return _conv_to_dict(convo)
                raise ValueError("Conversation not owned by user")

            now = datetime.now(timezone.utc)
            convo = ConversationRecord(
                id=conversation_id,
                user_id=user_id,
                org_id=org_id,
                title=title,
                created_at=now,
                updated_at=now,
            )
            session.add(convo)
            session.commit()
            return _conv_to_dict(convo)

    def create_conversation(self, user_id: str, title: str, org_id: str | None = None) -> dict:
        now = datetime.now(timezone.utc)
        convo = ConversationRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            org_id=org_id,
            title=title,
            created_at=now,
            updated_at=now,
        )
        with Session(self.engine) as session:
            session.add(convo)
            session.commit()
            return _conv_to_dict(convo)

    def save_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        chunks_json: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        generation_time_ms: int | None = None,
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
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                generation_time_ms=generation_time_ms,
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
            # Record message IDs for sync before cascade deletes them
            msg_ids = [
                m.id for m in
                session.query(MessageRecord.id)
                .filter(MessageRecord.conversation_id == conversation_id)
                .all()
            ]
            _record_delete(session, "messages", msg_ids)
            _record_delete(session, "conversations", [conversation_id])
            session.delete(convo)
            session.commit()
            return True

    def delete_conversation_admin(self, conversation_id: str) -> bool:
        """Delete a single conversation without ownership check (admin use)."""
        with Session(self.engine) as session:
            convo = session.get(ConversationRecord, conversation_id)
            if convo is None:
                return False
            msg_ids = [
                m.id for m in
                session.query(MessageRecord.id)
                .filter(MessageRecord.conversation_id == conversation_id)
                .all()
            ]
            _record_delete(session, "messages", msg_ids)
            _record_delete(session, "conversations", [conversation_id])
            session.delete(convo)
            session.commit()
            return True

    def search_conversations(self, user_id: str, query: str, limit: int = 20, org_id: str | None = None) -> list[dict]:
        """Search conversations by title and message content."""
        pattern = f"%{query}%"
        with Session(self.engine) as session:
            # Base filter: user + optional org scope
            base_filter = [ConversationRecord.user_id == user_id]
            if org_id is not None:
                base_filter.append(ConversationRecord.org_id == org_id)

            # Find conversations with matching titles
            title_matches = set(
                row[0]
                for row in session.execute(
                    select(ConversationRecord.id)
                    .where(*base_filter)
                    .where(ConversationRecord.title.ilike(pattern))
                ).all()
            )

            # Find conversations with matching message content
            msg_rows = (
                session.query(
                    MessageRecord.conversation_id,
                    MessageRecord.role,
                    MessageRecord.content,
                    MessageRecord.created_at,
                )
                .join(
                    ConversationRecord,
                    MessageRecord.conversation_id == ConversationRecord.id,
                )
                .filter(*base_filter)
                .filter(MessageRecord.content.ilike(pattern))
                .order_by(MessageRecord.created_at.desc())
                .all()
            )

            # Group matching messages by conversation
            msg_by_conv: dict[str, list[dict]] = {}
            for conv_id, role, content, created_at in msg_rows:
                if conv_id not in msg_by_conv:
                    msg_by_conv[conv_id] = []
                if len(msg_by_conv[conv_id]) < 3:  # max 3 snippets per conversation
                    # Extract snippet around the match
                    lower_content = content.lower()
                    idx = lower_content.find(query.lower())
                    start = max(0, idx - 40)
                    end = min(len(content), idx + len(query) + 40)
                    snippet = ("..." if start > 0 else "") + content[start:end] + ("..." if end < len(content) else "")
                    msg_by_conv[conv_id].append({
                        "role": role,
                        "snippet": snippet,
                        "created_at": _to_ist(created_at),
                    })

            # Collect all matching conversation IDs
            all_conv_ids = title_matches | set(msg_by_conv.keys())
            if not all_conv_ids:
                return []

            # Fetch conversation details
            convos = (
                session.query(ConversationRecord)
                .filter(ConversationRecord.id.in_(all_conv_ids))
                .order_by(desc(ConversationRecord.updated_at))
                .limit(limit)
                .all()
            )

            return [
                {
                    "id": c.id,
                    "title": c.title,
                    "is_starred": c.is_starred,
                    "updated_at": _to_ist(c.updated_at),
                    "title_match": c.id in title_matches,
                    "matching_messages": msg_by_conv.get(c.id, []),
                }
                for c in convos
            ]

    def rename_conversation(self, conversation_id: str, user_id: str, title: str) -> bool:
        with Session(self.engine) as session:
            convo = session.get(ConversationRecord, conversation_id)
            if convo is None or convo.user_id != user_id:
                return False
            convo.title = title
            convo.updated_at = datetime.now(timezone.utc)
            session.commit()
            return True

    def star_conversation(self, conversation_id: str, user_id: str, starred: bool) -> bool:
        with Session(self.engine) as session:
            convo = session.get(ConversationRecord, conversation_id)
            if convo is None or convo.user_id != user_id:
                return False
            convo.is_starred = starred
            session.commit()
            return True

    def get_conversation_admin(self, conversation_id: str) -> dict | None:
        """Get full conversation detail without ownership check (admin use)."""
        with Session(self.engine) as session:
            convo = session.get(ConversationRecord, conversation_id)
            if convo is None:
                return None

            messages = (
                session.query(MessageRecord)
                .filter(MessageRecord.conversation_id == conversation_id)
                .order_by(MessageRecord.created_at)
                .all()
            )
            return {
                **_conv_to_dict(convo),
                "user_id": convo.user_id,
                "org_id": convo.org_id,
                "messages": [
                    {
                        "id": m.id,
                        "role": m.role,
                        "content": m.content,
                        "chunks_json": m.chunks_json,
                        "feedback": m.feedback,
                        "feedback_comment": m.feedback_comment,
                        "input_tokens": m.input_tokens,
                        "output_tokens": m.output_tokens,
                        "generation_time_ms": m.generation_time_ms,
                        "created_at": _to_ist(m.created_at),
                    }
                    for m in messages
                ],
            }

    def get_all_users_with_stats(self, user_ids: set[str] | None = None, org_id: str | None = None) -> list[dict]:
        """Return all users with conversation/message counts (admin use).

        If *user_ids* is provided, only those users are returned (org-scoped admin).
        If *org_id* is provided, only conversations belonging to that org are counted.
        """
        from insightxpert.auth.models import User as UserModel
        with Session(self.engine) as session:
            # Build the conversation join condition — optionally org-scoped
            conv_join = UserModel.id == ConversationRecord.user_id
            if org_id is not None:
                conv_join = and_(conv_join, ConversationRecord.org_id == org_id)

            query = (
                session.query(
                    UserModel.id,
                    UserModel.email,
                    UserModel.is_active,
                    func.count(func.distinct(ConversationRecord.id)).label("conversation_count"),
                    func.count(MessageRecord.id).label("message_count"),
                    func.max(ConversationRecord.updated_at).label("last_active"),
                )
                .outerjoin(ConversationRecord, conv_join)
                .outerjoin(MessageRecord, ConversationRecord.id == MessageRecord.conversation_id)
            )
            if user_ids is not None:
                query = query.filter(UserModel.id.in_(user_ids))
            results = query.group_by(UserModel.id).all()
            return [
                {
                    "id": r.id,
                    "email": r.email,
                    "is_active": r.is_active,
                    "conversation_count": r.conversation_count,
                    "message_count": r.message_count,
                    "last_active": _to_ist(r.last_active) if r.last_active else None,
                }
                for r in results
            ]

    def delete_user_conversations(self, user_id: str) -> int:
        """Delete ALL conversations for a user. Returns count deleted."""
        with Session(self.engine) as session:
            conv_ids = [
                c.id for c in
                session.query(ConversationRecord.id)
                .filter(ConversationRecord.user_id == user_id)
                .all()
            ]
            if conv_ids:
                msg_ids = [
                    m.id for m in
                    session.query(MessageRecord.id)
                    .filter(MessageRecord.conversation_id.in_(conv_ids))
                    .all()
                ]
                _record_delete(session, "messages", msg_ids)
                _record_delete(session, "conversations", conv_ids)
                session.query(MessageRecord).filter(
                    MessageRecord.conversation_id.in_(conv_ids)
                ).delete(synchronize_session=False)
                session.query(ConversationRecord).filter(
                    ConversationRecord.user_id == user_id
                ).delete(synchronize_session=False)
            session.commit()
            return len(conv_ids)

    def _delete_convs_by_filter(self, session: Session, conv_filter) -> int:
        """Delete conversations matching the given SQLAlchemy filter expression, plus their messages."""
        conv_ids = [
            c.id for c in
            session.query(ConversationRecord.id).filter(conv_filter).all()
        ]
        if not conv_ids:
            session.commit()
            return 0
        msg_ids = [
            m.id for m in
            session.query(MessageRecord.id)
            .filter(MessageRecord.conversation_id.in_(conv_ids))
            .all()
        ]
        _record_delete(session, "messages", msg_ids)
        _record_delete(session, "conversations", conv_ids)
        session.query(MessageRecord).filter(
            MessageRecord.conversation_id.in_(conv_ids)
        ).delete(synchronize_session=False)
        session.query(ConversationRecord).filter(
            ConversationRecord.id.in_(conv_ids)
        ).delete(synchronize_session=False)
        session.commit()
        return len(conv_ids)

    def delete_conversations_for_users(self, user_ids: list[str]) -> int:
        """Delete ALL conversations for multiple users. Returns count deleted."""
        if not user_ids:
            return 0
        with Session(self.engine) as session:
            return self._delete_convs_by_filter(
                session, ConversationRecord.user_id.in_(user_ids)
            )

    def delete_conversations_by_org(self, user_id: str, org_id: str) -> int:
        """Delete conversations for a user that belong to a specific org. Returns count deleted."""
        with Session(self.engine) as session:
            return self._delete_convs_by_filter(
                session,
                (ConversationRecord.user_id == user_id) & (ConversationRecord.org_id == org_id),
            )

    def delete_conversations_by_org_all(self, org_id: str) -> int:
        """Delete ALL conversations belonging to an org. Returns count deleted."""
        with Session(self.engine) as session:
            return self._delete_convs_by_filter(
                session, ConversationRecord.org_id == org_id
            )

    def delete_all_conversations(self) -> int:
        """Delete ALL conversations across all users. Returns count deleted."""
        with Session(self.engine) as session:
            return self._delete_convs_by_filter(session, sa_true())

    def update_message_feedback(
        self,
        message_id: str,
        user_id: str,
        feedback: bool | None,
        comment: str | None = None,
    ) -> bool:
        with Session(self.engine) as session:
            msg = session.get(MessageRecord, message_id)
            if msg is None:
                return False
            # Verify the message belongs to a conversation owned by the user
            convo = session.get(ConversationRecord, msg.conversation_id)
            if convo is None or convo.user_id != user_id:
                return False
            msg.feedback = feedback
            msg.feedback_comment = comment
            session.commit()
            return True
