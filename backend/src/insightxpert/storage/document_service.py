"""Document service -- CRUD and context retrieval for uploaded PDF documents."""
from __future__ import annotations

import logging

from sqlalchemy import or_
from sqlalchemy.orm import Session

from insightxpert.auth.models import Document, _utcnow

logger = logging.getLogger("insightxpert.storage")


class DocumentService:
    """Provides document CRUD and context markdown for the LLM agent."""

    def __init__(self, engine) -> None:
        self._engine = engine

    def create_document(
        self,
        *,
        doc_id: str,
        name: str,
        description: str | None,
        file_name: str,
        file_type: str,
        file_size_bytes: int,
        r2_key: str | None,
        extracted_text: str | None,
        page_count: int,
        dataset_id: str | None,
        created_by: str,
        org_id: str | None,
    ) -> dict:
        """Create a Document record and return it as a dict."""
        now = _utcnow()
        with Session(self._engine) as session:
            doc = Document(
                id=doc_id,
                name=name,
                description=description,
                file_name=file_name,
                file_type=file_type,
                file_size_bytes=file_size_bytes,
                r2_key=r2_key,
                extracted_text=extracted_text,
                page_count=page_count,
                dataset_id=dataset_id,
                created_by=created_by,
                org_id=org_id,
                created_at=now,
                updated_at=now,
            )
            session.add(doc)
            session.commit()
            return self._to_dict(doc)

    def list_documents(
        self,
        *,
        user_id: str | None = None,
        is_super_admin: bool = False,
    ) -> list[dict]:
        """Return documents visible to the caller.

        Visibility rules for user-uploaded documents (created_by IS NOT NULL):
        - Super admins see everything.
        - Regular users see only their own uploads.
        System documents (created_by IS NULL) are always visible.
        """
        with Session(self._engine) as session:
            q = session.query(Document).order_by(Document.created_at.desc())

            if not is_super_admin and user_id is not None:
                q = q.filter(
                    or_(
                        Document.created_by.is_(None),   # system documents
                        Document.created_by == user_id,   # own uploads
                    )
                )

            return [self._to_dict(doc) for doc in q.all()]

    def get_document_by_id(self, doc_id: str) -> dict | None:
        """Return a single document dict, or None."""
        with Session(self._engine) as session:
            doc = session.get(Document, doc_id)
            if not doc:
                return None
            return self._to_dict(doc)

    def delete_document(
        self,
        doc_id: str,
        user_id: str,
        is_admin: bool,
    ):
        """Delete a document record.

        Returns the r2_key for cleanup on success, False if not found.
        Raises PermissionError if the user is not the owner and not an admin.
        """
        with Session(self._engine) as session:
            doc = session.get(Document, doc_id)
            if not doc:
                return False

            # Ownership check
            if not is_admin and doc.created_by != user_id:
                raise PermissionError("You can only delete documents you uploaded")

            r2_key = doc.r2_key
            session.delete(doc)
            session.commit()
            return r2_key

    def get_documents_context_markdown(self, dataset_id: str | None = None) -> str:
        """Build markdown from extracted text for LLM context injection.

        Optionally filter by dataset_id.  Returns empty string if no documents.
        """
        with Session(self._engine) as session:
            q = session.query(Document).order_by(Document.created_at)
            if dataset_id is not None:
                q = q.filter(Document.dataset_id == dataset_id)

            docs = q.all()
            if not docs:
                return ""

            sections: list[str] = ["## Uploaded Reference Documents"]
            for doc in docs:
                if not doc.extracted_text:
                    continue
                header = f"### {doc.name}"
                if doc.description:
                    header += f"\n{doc.description}"
                sections.append(f"{header}\n\n{doc.extracted_text}")

            if len(sections) <= 1:
                return ""

            return "\n\n".join(sections)

    @staticmethod
    def _to_dict(doc: Document) -> dict:
        preview = None
        if doc.extracted_text:
            preview = doc.extracted_text[:500]
            if len(doc.extracted_text) > 500:
                preview += "..."
        return {
            "id": doc.id,
            "name": doc.name,
            "description": doc.description,
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "file_size_bytes": doc.file_size_bytes,
            "r2_key": doc.r2_key,
            "page_count": doc.page_count,
            "extracted_text_preview": preview,
            "dataset_id": doc.dataset_id,
            "created_by": doc.created_by,
            "org_id": doc.org_id,
            "created_at": str(doc.created_at),
            "updated_at": str(doc.updated_at),
        }
