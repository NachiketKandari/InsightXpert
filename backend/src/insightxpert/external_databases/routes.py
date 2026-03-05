import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from insightxpert.admin.dependencies import require_admin_user
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import User
from insightxpert.external_databases.schemas import (
    CreateExternalDatabase,
    CreateUserDatabaseConnection,
    ExternalDatabaseResponse,
    SetActiveRequest,
    TestConnectionResponse,
    UpdateExternalDatabase,
    UserDatabaseConnectionResponse,
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


# ---------------------------------------------------------------------------
# User-scoped database connections
# ---------------------------------------------------------------------------

user_connections_router = APIRouter(
    prefix="/api/connections", tags=["user-connections"]
)


def _get_user_db_service(request: Request):
    svc = getattr(request.app.state, "user_db_service", None)
    if svc is None:
        raise HTTPException(
            status_code=503, detail="User database service not available"
        )
    return svc


@user_connections_router.get("", response_model=list[UserDatabaseConnectionResponse])
async def list_user_connections(
    request: Request,
    user: User = Depends(get_current_user),
):
    svc = _get_user_db_service(request)
    results = await asyncio.to_thread(svc.list_connections, user_id=user.id)
    return results


@user_connections_router.post("", response_model=UserDatabaseConnectionResponse)
async def create_user_connection(
    request: Request,
    body: CreateUserDatabaseConnection,
    user: User = Depends(get_current_user),
):
    svc = _get_user_db_service(request)
    result = await asyncio.to_thread(
        svc.create_connection,
        user_id=user.id,
        name=body.name,
        connection_string=body.connection_string,
    )
    return result


@user_connections_router.delete("/{conn_id}")
async def delete_user_connection(
    request: Request,
    conn_id: str,
    user: User = Depends(get_current_user),
):
    svc = _get_user_db_service(request)
    deleted = await asyncio.to_thread(
        svc.delete_connection, conn_id=conn_id, user_id=user.id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"status": "ok"}


@user_connections_router.patch(
    "/{conn_id}/active", response_model=UserDatabaseConnectionResponse
)
async def set_user_connection_active(
    request: Request,
    conn_id: str,
    body: SetActiveRequest,
    user: User = Depends(get_current_user),
):
    svc = _get_user_db_service(request)
    result = await asyncio.to_thread(
        svc.set_active, conn_id=conn_id, user_id=user.id, active=body.active
    )
    if not result:
        raise HTTPException(status_code=404, detail="Connection not found")
    return result


@user_connections_router.post(
    "/{conn_id}/test", response_model=TestConnectionResponse
)
async def test_user_connection(
    request: Request,
    conn_id: str,
    user: User = Depends(get_current_user),
):
    svc = _get_user_db_service(request)
    result = await svc.test_connection(conn_id=conn_id, user_id=user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Connection not found")
    return result
