"""Admin API routes for dataset management."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from insightxpert.admin.dependencies import require_super_admin_user
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import User
from insightxpert.datasets.dependencies import ResolvedUser, resolve_user_roles
from insightxpert.datasets.service import DatasetService

logger = logging.getLogger("insightxpert.datasets")


router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _get_dataset_service(request: Request) -> DatasetService:
    svc = getattr(request.app.state, "dataset_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Dataset service not available")
    return svc


# --- Request/response models ---

class DatasetUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    ddl: str | None = None
    documentation: str | None = None
    organization_id: str | None = None


class ColumnRequest(BaseModel):
    column_name: str
    column_type: str = "TEXT"
    description: str | None = None
    domain_values: str | None = None
    domain_rules: str | None = None
    ordinal_position: int = 0


class ColumnProfileModel(BaseModel):
    name: str
    original_name: str
    inferred_type: str
    distinct_count: int
    null_count: int
    null_percent: float
    is_unique: bool
    cardinality: str
    unique_values: list[str] | None = None
    min: float | None = None
    max: float | None = None
    mean: float | None = None


class DatasetProfileModel(BaseModel):
    row_count: int
    column_count: int
    columns: list[ColumnProfileModel]


class ConfirmDatasetRequest(BaseModel):
    column_descriptions: dict[str, str] = {}
    profile: DatasetProfileModel


class ExampleQueryRequest(BaseModel):
    question: str
    sql: str
    category: str | None = None


# --- Endpoints ---

@router.get("")
async def list_datasets(
    request: Request,
    user: User = Depends(require_super_admin_user),
):
    svc = _get_dataset_service(request)
    return await asyncio.to_thread(svc.list_datasets)


@router.get("/public")
async def list_datasets_public(
    request: Request,
    roles: ResolvedUser = Depends(resolve_user_roles),
):
    """List datasets visible to the current user.

    User-uploaded datasets are user-scoped: only the uploader and super
    admins (admin with no org) can see them.  System datasets (created_by
    IS NULL) are visible to everyone.
    """
    svc = _get_dataset_service(request)

    datasets = await asyncio.to_thread(
        svc.list_datasets,
        user_id=roles.user.id,
        is_super_admin=roles.is_super_admin,
    )
    return [
        {
            "id": ds["id"],
            "name": ds["name"],
            "description": ds.get("description"),
            "is_active": ds["is_active"],
            "table_name": ds.get("table_name"),
            "organization_id": ds.get("organization_id"),
            "created_by": ds.get("created_by"),
        }
        for ds in datasets
    ]


@router.get("/public/{dataset_id}/columns")
async def get_dataset_columns_public(
    dataset_id: str,
    request: Request,
    roles: ResolvedUser = Depends(resolve_user_roles),
):
    """Return column metadata for a dataset.

    Enforces user-scope: if the dataset was uploaded by another user,
    only the owner or a super admin may access its columns.
    """
    svc = _get_dataset_service(request)
    ds = await asyncio.to_thread(svc.get_dataset_by_id, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Enforce user-scope for uploaded datasets
    if ds.get("created_by") is not None and ds["created_by"] != roles.user.id:
        if not roles.is_super_admin:
            raise HTTPException(status_code=403, detail="Access denied")

    cols = await asyncio.to_thread(svc.get_dataset_columns, dataset_id)
    return cols


@router.post("/upload")
async def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str | None = Form(None),
    user: User = Depends(get_current_user),
):
    """Upload a CSV file to create a new dataset.

    Any authenticated user can upload. The dataset is created inactive
    and owned by the uploading user.  The file is streamed to a temp
    file on disk so that large CSVs (up to 500 MB) never need to be
    held entirely in memory.
    """
    MAX_CSV_SIZE = 500 * 1024 * 1024  # 500 MB
    CHUNK_SIZE = 256 * 1024  # 256 KB read chunks

    # Validate file extension
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are supported. Please upload a .csv file.",
        )

    # Check file size hint before streaming (Content-Length may be set)
    if file.size and file.size > MAX_CSV_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_CSV_SIZE // (1024 * 1024)} MB.",
        )

    # Stream upload to a temp file — keeps memory bounded at ~256 KB
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    csv_path = Path(tmp.name)
    try:
        bytes_written = 0
        try:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > MAX_CSV_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size is {MAX_CSV_SIZE // (1024 * 1024)} MB.",
                    )
                tmp.write(chunk)
        finally:
            tmp.close()  # always close before unlink or further work

        if bytes_written == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        svc = _get_dataset_service(request)

        try:
            result = await asyncio.to_thread(
                svc.create_dataset_from_csv_file,
                name=name,
                description=description,
                created_by=user.id,
                org_id=user.org_id,
                csv_path=csv_path,
                file_name=file.filename,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        logger.info("User %s uploaded dataset '%s' (%s, %d bytes)", user.id, name, file.filename, bytes_written)

        # Fire-and-forget R2 backup (streams from disk, no memory spike)
        r2 = getattr(request.app.state, "r2_storage", None)
        if r2 is not None:
            r2_key = f"uploads/{user.id}/{result['id']}/{file.filename}"
            # Keep csv_path alive until R2 upload completes
            r2_csv_path = str(csv_path)
            async def _r2_upload():
                try:
                    ok = await asyncio.to_thread(
                        r2.upload_file_from_path, r2_key, r2_csv_path, "text/csv",
                    )
                    if ok:
                        await asyncio.to_thread(svc.update_dataset, result["id"], r2_key=r2_key)
                        logger.info("R2 backup stored: %s", r2_key)
                finally:
                    Path(r2_csv_path).unlink(missing_ok=True)
            task = asyncio.create_task(_r2_upload())
            def _log_r2_failure(t: asyncio.Task) -> None:
                if not t.cancelled() and t.exception():
                    logger.error("R2 background upload failed: %s", t.exception())
            task.add_done_callback(_log_r2_failure)
        else:
            # No R2 configured — clean up the temp file now
            csv_path.unlink(missing_ok=True)

        return result
    except Exception:
        # Ensure temp file is cleaned up on any error path
        csv_path.unlink(missing_ok=True)
        raise


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    request: Request,
    roles: ResolvedUser = Depends(resolve_user_roles),
):
    """Delete a dataset and its data table.

    Owners can delete their own datasets; admins can delete any dataset.
    """
    svc = _get_dataset_service(request)

    # Get r2_key before deletion for cleanup
    ds_info = await asyncio.to_thread(svc.get_dataset_by_id, dataset_id)
    r2_key = ds_info.get("r2_key") if ds_info else None

    try:
        deleted = await asyncio.to_thread(
            svc.delete_dataset, dataset_id, roles.user.id, roles.is_admin,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found")

    logger.info("User %s deleted dataset %s", roles.user.id, dataset_id)

    # Fire-and-forget R2 cleanup
    r2 = getattr(request.app.state, "r2_storage", None)
    if r2 is not None and r2_key:
        task = asyncio.create_task(asyncio.to_thread(r2.delete_file, r2_key))
        task.add_done_callback(lambda t: None if t.cancelled() else t.exception())

    return {"status": "ok"}


COLUMN_SCOPING_THRESHOLD = 20


@router.post("/{dataset_id}/confirm")
async def confirm_dataset(
    dataset_id: str,
    body: ConfirmDatasetRequest,
    request: Request,
    roles: ResolvedUser = Depends(resolve_user_roles),
):
    """Confirm a dataset after upload by providing column descriptions.

    Compiles rich documentation from the profiler output and user-provided
    descriptions.  Only the dataset owner or an admin can confirm.

    For datasets with more than ``COLUMN_SCOPING_THRESHOLD`` columns, each
    column's description is also embedded into the ``column_metadata`` vector
    store collection.  This enables the analyst to retrieve only the
    semantically relevant columns at query time, keeping the SQL prompt tight.
    """
    svc = _get_dataset_service(request)

    try:
        result = await asyncio.to_thread(
            svc.confirm_dataset,
            dataset_id,
            roles.user.id,
            roles.is_admin,
            body.column_descriptions,
            body.profile.model_dump(),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    if not result:
        raise HTTPException(status_code=404, detail="Dataset not found")

    logger.info("User %s confirmed dataset %s", roles.user.id, dataset_id)

    # Embed per-column descriptions for wide datasets (>COLUMN_SCOPING_THRESHOLD columns)
    # so the analyst can do semantic column retrieval at query time.
    if body.profile.column_count > COLUMN_SCOPING_THRESHOLD:
        rag = getattr(request.app.state, "rag", None)
        if rag is not None:
            from insightxpert.training.trainer import Trainer
            trainer = Trainer(rag)
            try:
                n_embedded = await asyncio.to_thread(
                    trainer.embed_columns_for_dataset, svc, dataset_id,
                )
                logger.info(
                    "Embedded %d column descriptions for wide dataset %s (%d columns)",
                    n_embedded, dataset_id, body.profile.column_count,
                )
            except Exception:
                logger.warning(
                    "Column embedding failed for dataset %s — column scoping will be unavailable",
                    dataset_id, exc_info=True,
                )

    return result


@router.get("/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    request: Request,
    user: User = Depends(require_super_admin_user),
):
    svc = _get_dataset_service(request)
    ds = await asyncio.to_thread(svc.get_dataset_by_id, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    ds["columns"] = await asyncio.to_thread(svc.get_dataset_columns, dataset_id)
    ds["example_queries"] = await asyncio.to_thread(svc.get_example_queries, dataset_id)
    return ds


@router.put("/{dataset_id}")
async def update_dataset(
    dataset_id: str,
    body: DatasetUpdateRequest,
    request: Request,
    user: User = Depends(require_super_admin_user),
):
    svc = _get_dataset_service(request)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await asyncio.to_thread(svc.update_dataset, dataset_id, **fields)
    if not result:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return result


@router.post("/{dataset_id}/columns")
async def add_column(
    dataset_id: str,
    body: ColumnRequest,
    request: Request,
    user: User = Depends(require_super_admin_user),
):
    svc = _get_dataset_service(request)
    result = await asyncio.to_thread(svc.add_column, dataset_id, **body.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return result


@router.put("/{dataset_id}/columns/{col_id}")
async def update_column(
    dataset_id: str,
    col_id: str,
    body: ColumnRequest,
    request: Request,
    user: User = Depends(require_super_admin_user),
):
    svc = _get_dataset_service(request)
    result = await asyncio.to_thread(svc.update_column, dataset_id, col_id, **body.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Column not found")
    return result


@router.post("/{dataset_id}/queries")
async def add_example_query(
    dataset_id: str,
    body: ExampleQueryRequest,
    request: Request,
    user: User = Depends(require_super_admin_user),
):
    svc = _get_dataset_service(request)
    result = await asyncio.to_thread(svc.add_example_query, dataset_id, **body.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return result


@router.delete("/{dataset_id}/queries/{query_id}")
async def delete_example_query(
    dataset_id: str,
    query_id: str,
    request: Request,
    user: User = Depends(require_super_admin_user),
):
    svc = _get_dataset_service(request)
    deleted = await asyncio.to_thread(svc.delete_example_query, dataset_id, query_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Example query not found")
    return {"status": "ok"}


@router.post("/{dataset_id}/activate")
async def activate_dataset(
    dataset_id: str,
    request: Request,
    roles: ResolvedUser = Depends(resolve_user_roles),
):
    svc = _get_dataset_service(request)
    ds = await asyncio.to_thread(svc.get_dataset_by_id, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # System datasets (created_by is None) can be activated by anyone.
    # User-uploaded datasets can only be activated by the owner or a super admin.
    if ds.get("created_by") is not None and ds["created_by"] != roles.user.id:
        if not roles.is_super_admin:
            raise HTTPException(status_code=403, detail="Access denied")

    ok = await asyncio.to_thread(svc.activate_dataset, dataset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"status": "ok", "active_dataset_id": dataset_id}


@router.post("/{dataset_id}/retrain")
async def retrain_dataset(
    dataset_id: str,
    request: Request,
    user: User = Depends(require_super_admin_user),
):
    """Re-run RAG training for a specific dataset."""
    svc = _get_dataset_service(request)

    ds = await asyncio.to_thread(svc.get_dataset_by_id, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    rag = request.app.state.rag
    from insightxpert.training.trainer import Trainer
    trainer = Trainer(rag)
    count = await asyncio.to_thread(trainer.train_from_dataset, svc)
    return {"status": "ok", "items_trained": count}
