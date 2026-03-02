"""Admin API routes for dataset management."""

from __future__ import annotations

import asyncio
import logging

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
    and owned by the uploading user.
    """
    MAX_CSV_SIZE = 50 * 1024 * 1024  # 50 MB

    # Validate file extension
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are supported. Please upload a .csv file.",
        )

    # Check file size hint before reading
    if file.size and file.size > MAX_CSV_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_CSV_SIZE // (1024 * 1024)} MB.",
        )

    # Read file content
    csv_content = await file.read()
    if not csv_content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    if len(csv_content) > MAX_CSV_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_CSV_SIZE // (1024 * 1024)} MB.",
        )

    svc = _get_dataset_service(request)

    try:
        result = await asyncio.to_thread(
            svc.create_dataset_from_csv,
            name=name,
            description=description,
            created_by=user.id,
            org_id=user.org_id,
            csv_content=csv_content,
            file_name=file.filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    logger.info("User %s uploaded dataset '%s' (%s)", user.id, name, file.filename)

    # Fire-and-forget R2 backup
    r2 = getattr(request.app.state, "r2_storage", None)
    if r2 is not None:
        r2_key = f"uploads/{user.id}/{result['id']}/{file.filename}"
        async def _r2_upload():
            try:
                ok = await asyncio.to_thread(r2.upload_file, r2_key, csv_content, "text/csv")
                if ok:
                    await asyncio.to_thread(svc.update_dataset, result["id"], r2_key=r2_key)
                    logger.info("R2 backup stored: %s", r2_key)
            except Exception as e:
                logger.warning("R2 backup failed for dataset %s: %s", result["id"], e)
        task = asyncio.create_task(_r2_upload())
        task.add_done_callback(lambda t: None if t.cancelled() else t.exception())

    return result


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
