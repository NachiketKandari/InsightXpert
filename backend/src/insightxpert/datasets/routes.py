"""Admin API routes for dataset management."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import User
from insightxpert.datasets.service import DatasetService

logger = logging.getLogger("insightxpert.datasets")

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _get_dataset_service(request: Request) -> DatasetService:
    svc = getattr(request.app.state, "dataset_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Dataset service not available")
    return svc


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")


# --- Request/response models ---

class DatasetUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    ddl: str | None = None
    documentation: str | None = None


class ColumnRequest(BaseModel):
    column_name: str
    column_type: str = "TEXT"
    description: str | None = None
    domain_values: str | None = None
    domain_rules: str | None = None
    ordinal_position: int = 0


class ExampleQueryRequest(BaseModel):
    question: str
    sql: str
    category: str | None = None


# --- Endpoints ---

@router.get("")
async def list_datasets(
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_dataset_service(request)
    return svc.list_datasets()


@router.get("/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_dataset_service(request)
    ds = svc.get_dataset_by_id(dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    ds["columns"] = svc.get_dataset_columns(dataset_id)
    ds["example_queries"] = svc.get_example_queries(dataset_id)
    return ds


@router.put("/{dataset_id}")
async def update_dataset(
    dataset_id: str,
    body: DatasetUpdateRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_dataset_service(request)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = svc.update_dataset(dataset_id, **fields)
    if not result:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return result


@router.post("/{dataset_id}/columns")
async def add_column(
    dataset_id: str,
    body: ColumnRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_dataset_service(request)
    result = svc.add_column(dataset_id, **body.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return result


@router.put("/{dataset_id}/columns/{col_id}")
async def update_column(
    dataset_id: str,
    col_id: str,
    body: ColumnRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_dataset_service(request)
    result = svc.update_column(dataset_id, col_id, **body.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Column not found")
    return result


@router.post("/{dataset_id}/queries")
async def add_example_query(
    dataset_id: str,
    body: ExampleQueryRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_dataset_service(request)
    result = svc.add_example_query(dataset_id, **body.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return result


@router.delete("/{dataset_id}/queries/{query_id}")
async def delete_example_query(
    dataset_id: str,
    query_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_dataset_service(request)
    deleted = svc.delete_example_query(dataset_id, query_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Example query not found")
    return {"status": "ok"}


@router.post("/{dataset_id}/activate")
async def activate_dataset(
    dataset_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_dataset_service(request)
    ok = svc.activate_dataset(dataset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"status": "ok", "active_dataset_id": dataset_id}


@router.post("/{dataset_id}/retrain")
async def retrain_dataset(
    dataset_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Re-run RAG training for a specific dataset."""
    _require_admin(user)
    svc = _get_dataset_service(request)

    ds = svc.get_dataset_by_id(dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    rag = request.app.state.rag
    from insightxpert.training.trainer import Trainer
    trainer = Trainer(rag)
    count = await asyncio.to_thread(trainer.train_from_dataset, svc)
    return {"status": "ok", "items_trained": count}
