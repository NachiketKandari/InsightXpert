"""Document API routes."""
from __future__ import annotations
import asyncio
import logging
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from insightxpert.admin.config_store import read_config
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import User, _uuid
from insightxpert.auth.permissions import is_admin_user

logger = logging.getLogger("insightxpert.storage")
router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_PDF_SIZE = 20 * 1024 * 1024  # 20 MB


def _get_document_service(request: Request):
    svc = getattr(request.app.state, "document_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Document service not available")
    return svc


@router.post("/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str | None = Form(None),
    dataset_id: str | None = Form(None),
    user: User = Depends(get_current_user),
):
    # Validate PDF
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    if file.size and file.size > MAX_PDF_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum is {MAX_PDF_SIZE // (1024*1024)} MB.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > MAX_PDF_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum is {MAX_PDF_SIZE // (1024*1024)} MB.")

    # Extract text
    from insightxpert.storage.pdf_extractor import extract_text_from_pdf
    try:
        extracted_text, page_count = await asyncio.to_thread(extract_text_from_pdf, content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to process PDF: {exc}")

    svc = _get_document_service(request)

    # R2 upload (fire-and-forget)
    doc_id = _uuid()
    r2_key = f"documents/{user.id}/{doc_id}/{file.filename}"

    r2 = getattr(request.app.state, "r2_storage", None)
    if r2 is not None:
        async def _r2_upload():
            try:
                await asyncio.to_thread(r2.upload_file, r2_key, content, "application/pdf")
                logger.info("R2 upload stored: %s", r2_key)
            except Exception as e:
                logger.warning("R2 upload failed for document %s: %s", doc_id, e)
        asyncio.ensure_future(_r2_upload())

    # Create DB record
    try:
        result = await asyncio.to_thread(
            svc.create_document,
            doc_id=doc_id,
            name=name,
            description=description,
            file_name=file.filename,
            file_type="application/pdf",
            file_size_bytes=len(content),
            r2_key=r2_key if r2 else None,
            extracted_text=extracted_text,
            page_count=page_count,
            dataset_id=dataset_id,
            created_by=user.id,
            org_id=user.org_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    logger.info("User %s uploaded document '%s' (%s, %d pages)", user.id, name, file.filename, page_count)
    return result


@router.get("")
async def list_documents(
    request: Request,
    user: User = Depends(get_current_user),
):
    svc = _get_document_service(request)
    config = await asyncio.to_thread(read_config, request.app.state.auth_engine)
    admin = is_admin_user(user, config.admin_domains)
    super_admin = admin and user.org_id is None

    docs = await asyncio.to_thread(svc.list_documents, user_id=user.id, is_super_admin=super_admin)
    return docs


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    svc = _get_document_service(request)
    config = await asyncio.to_thread(read_config, request.app.state.auth_engine)
    admin = is_admin_user(user, config.admin_domains)

    try:
        r2_key = await asyncio.to_thread(svc.delete_document, doc_id, user.id, admin)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    if r2_key is False:
        raise HTTPException(status_code=404, detail="Document not found")

    # Fire-and-forget R2 cleanup
    r2 = getattr(request.app.state, "r2_storage", None)
    if r2 is not None and r2_key:
        asyncio.ensure_future(asyncio.to_thread(r2.delete_file, r2_key))

    logger.info("User %s deleted document %s", user.id, doc_id)
    return {"status": "ok"}
