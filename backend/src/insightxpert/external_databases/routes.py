import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from insightxpert.admin.dependencies import require_admin_user
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import User
from insightxpert.external_databases.schemas import (
    CreateExternalDatabase,
    ExternalDatabaseResponse,
    TestConnectionResponse,
    UpdateExternalDatabase,
)

logger = logging.getLogger("insightxpert.external_databases")

router = APIRouter(prefix="/api/external-databases", tags=["external-databases"])


def _get_service(request: Request):
    svc = getattr(request.app.state, "external_db_service", None)
    if svc is None:
        raise HTTPException(
            status_code=503, detail="External database service not available"
        )
    return svc


class RefreshSchemaResponse(BaseModel):
    success: bool
    message: str
    table_count: int


@router.post("", response_model=ExternalDatabaseResponse)
async def create_external_database(
    request: Request,
    body: CreateExternalDatabase,
    user: User = Depends(require_admin_user),
):
    svc = _get_service(request)
    result = await asyncio.to_thread(
        svc.create_external_database,
        name=body.name,
        connection_type=body.connection_type,
        host=body.host,
        port=body.port,
        database=body.database,
        username=body.username,
        password=body.password,
        organization_id=user.org_id,
    )
    return result


@router.get("", response_model=list[ExternalDatabaseResponse])
async def list_external_databases(
    request: Request,
    user: User = Depends(get_current_user),
):
    svc = _get_service(request)
    results = await asyncio.to_thread(
        svc.get_external_databases,
        organization_id=user.org_id,
    )
    return results


@router.get("/{db_id}", response_model=ExternalDatabaseResponse)
async def get_external_database(
    request: Request,
    db_id: str,
    user: User = Depends(get_current_user),
):
    svc = _get_service(request)
    result = await asyncio.to_thread(
        svc.get_external_database,
        db_id=db_id,
        organization_id=user.org_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="External database not found")
    return result


@router.put("/{db_id}", response_model=ExternalDatabaseResponse)
async def update_external_database(
    request: Request,
    db_id: str,
    body: UpdateExternalDatabase,
    user: User = Depends(require_admin_user),
):
    svc = _get_service(request)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await asyncio.to_thread(
        svc.update_external_database,
        db_id=db_id,
        organization_id=user.org_id,
        **fields,
    )
    if not result:
        raise HTTPException(status_code=404, detail="External database not found")
    return result


@router.delete("/{db_id}")
async def delete_external_database(
    request: Request,
    db_id: str,
    user: User = Depends(require_admin_user),
):
    svc = _get_service(request)
    deleted = await asyncio.to_thread(
        svc.delete_external_database,
        db_id=db_id,
        organization_id=user.org_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="External database not found")
    return {"status": "ok"}


@router.post("/{db_id}/test", response_model=TestConnectionResponse)
async def test_external_database_connection(
    request: Request,
    db_id: str,
    user: User = Depends(require_admin_user),
):
    svc = _get_service(request)
    result = await svc.test_connection(
        db_id=db_id,
        organization_id=user.org_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="External database not found")
    return result


@router.post("/{db_id}/refresh-schema", response_model=RefreshSchemaResponse)
async def refresh_external_database_schema(
    request: Request,
    db_id: str,
    user: User = Depends(require_admin_user),
):
    svc = _get_service(request)
    rag = getattr(request.app.state, "rag", None)
    if rag is None:
        raise HTTPException(status_code=503, detail="RAG store not available")

    result = await svc.refresh_schema(
        db_id=db_id,
        organization_id=user.org_id,
        rag_store=rag,
    )
    if not result:
        raise HTTPException(status_code=404, detail="External database not found")
    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("message", "Schema refresh failed")
        )
    return result
