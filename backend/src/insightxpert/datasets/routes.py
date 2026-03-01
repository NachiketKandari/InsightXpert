"""Admin API routes for dataset management."""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from sqlalchemy.orm import Session as SASession

from insightxpert.admin.config_store import read_config
from insightxpert.auth.dependencies import get_current_user, require_admin
from insightxpert.auth.models import User
from insightxpert.auth.models import User as UserModel
from insightxpert.datasets.service import DatasetService

logger = logging.getLogger("insightxpert.datasets")


def _extract_table_name(ddl: str) -> str | None:
    m = re.search(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?(\w+)["`]?',
        ddl,
        re.IGNORECASE,
    )
    return m.group(1) if m else None

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _get_dataset_service(request: Request) -> DatasetService:
    svc = getattr(request.app.state, "dataset_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Dataset service not available")
    return svc


def _get_admin_domains(request: Request) -> list[str]:
    """Read admin_domains from the persisted config."""
    engine = request.app.state.auth_engine
    config = read_config(engine)
    return config.admin_domains


def _require_super_admin_for_datasets(request: Request, user: User) -> None:
    """Raise 403 if the admin is org-scoped (not a super admin)."""
    engine = request.app.state.auth_engine
    with SASession(engine) as session:
        db_user = session.get(UserModel, user.id)
        if db_user is not None and db_user.org_id is not None:
            raise HTTPException(
                status_code=403,
                detail="Dataset management requires super-admin access",
            )


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
    require_admin(user, _get_admin_domains(request))
    _require_super_admin_for_datasets(request, user)
    svc = _get_dataset_service(request)
    return await asyncio.to_thread(svc.list_datasets)


@router.get("/public")
async def list_datasets_public(
    request: Request,
    user: User = Depends(get_current_user),
):
    """List datasets for any authenticated user (minimal info, no admin required)."""
    svc = _get_dataset_service(request)
    datasets = await asyncio.to_thread(svc.list_datasets)
    return [
        {
            "id": ds["id"],
            "name": ds["name"],
            "description": ds.get("description"),
            "is_active": ds["is_active"],
            "organization_id": ds.get("organization_id"),
            "table_name": _extract_table_name(ds.get("ddl", "")),
        }
        for ds in datasets
    ]


@router.get("/public/{dataset_id}/columns")
async def get_dataset_columns_public(
    dataset_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Return column metadata for a dataset (no admin required)."""
    svc = _get_dataset_service(request)
    cols = await asyncio.to_thread(svc.get_dataset_columns, dataset_id)
    return cols


@router.get("/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    require_admin(user, _get_admin_domains(request))
    _require_super_admin_for_datasets(request, user)
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
    user: User = Depends(get_current_user),
):
    require_admin(user, _get_admin_domains(request))
    _require_super_admin_for_datasets(request, user)
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
    user: User = Depends(get_current_user),
):
    require_admin(user, _get_admin_domains(request))
    _require_super_admin_for_datasets(request, user)
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
    user: User = Depends(get_current_user),
):
    require_admin(user, _get_admin_domains(request))
    _require_super_admin_for_datasets(request, user)
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
    user: User = Depends(get_current_user),
):
    require_admin(user, _get_admin_domains(request))
    _require_super_admin_for_datasets(request, user)
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
    user: User = Depends(get_current_user),
):
    require_admin(user, _get_admin_domains(request))
    _require_super_admin_for_datasets(request, user)
    svc = _get_dataset_service(request)
    deleted = await asyncio.to_thread(svc.delete_example_query, dataset_id, query_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Example query not found")
    return {"status": "ok"}


@router.post("/{dataset_id}/activate")
async def activate_dataset(
    dataset_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    require_admin(user, _get_admin_domains(request))
    _require_super_admin_for_datasets(request, user)
    svc = _get_dataset_service(request)
    ok = await asyncio.to_thread(svc.activate_dataset, dataset_id)
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
    require_admin(user, _get_admin_domains(request))
    _require_super_admin_for_datasets(request, user)
    svc = _get_dataset_service(request)

    ds = await asyncio.to_thread(svc.get_dataset_by_id, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    rag = request.app.state.rag
    from insightxpert.training.trainer import Trainer
    trainer = Trainer(rag)
    count = await asyncio.to_thread(trainer.train_from_dataset, svc)
    return {"status": "ok", "items_trained": count}
