from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from insightxpert.auth.conversation_store import PersistentConversationStore
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import User

logger = logging.getLogger("insightxpert.insights")

router = APIRouter(prefix="/api/insights", tags=["insights"])


def _get_store(request: Request) -> PersistentConversationStore:
    return request.app.state.persistent_conv_store


# --- Admin scoping (mirrors admin/routes.py pattern) --------------------------

class _AdminContext:
    __slots__ = ("user", "scoped_user_ids", "scoped_org_id")

    def __init__(self, user: User, scoped_user_ids: set[str] | None, scoped_org_id: str | None) -> None:
        self.user = user
        self.scoped_user_ids = scoped_user_ids
        self.scoped_org_id = scoped_org_id


def _get_admin_context(request: Request, user: User = Depends(get_current_user)) -> _AdminContext:
    from insightxpert.admin.config_store import read_config
    from insightxpert.auth.dependencies import require_admin
    from insightxpert.admin.routes import _resolve_admin_scope

    engine = request.app.state.auth_engine
    config = read_config(engine)
    require_admin(user, config.admin_domains)
    scoped_ids, scoped_org_id = _resolve_admin_scope(user, engine)
    return _AdminContext(user, scoped_ids, scoped_org_id)


# --- Request / response models -----------------------------------------------

class BookmarkRequest(BaseModel):
    bookmarked: bool


class CreateInsightRequest(BaseModel):
    message_id: str
    user_note: str | None = None


# --- User endpoints -----------------------------------------------------------

@router.post("")
async def create_insight(
    body: CreateInsightRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Create a manual insight from an assistant message."""
    store = _get_store(request)
    insight_id = await asyncio.to_thread(
        store.create_insight_from_message, user.id, user.org_id, body.message_id, body.user_note,
    )
    if insight_id is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "ok", "insight_id": insight_id}


@router.get("")
async def list_insights(
    request: Request,
    user: User = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    bookmarked: bool = Query(default=False),
):
    """List current user's insights (paginated, optional bookmark filter)."""
    store = _get_store(request)
    return await asyncio.to_thread(
        store.get_insights, user.id, user.org_id, limit, offset, bookmarked,
    )


@router.get("/all")
async def list_insights_admin(
    request: Request,
    ctx: _AdminContext = Depends(_get_admin_context),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Admin-scoped insights list."""
    store = _get_store(request)
    return await asyncio.to_thread(
        store.get_insights_admin, ctx.scoped_user_ids, ctx.scoped_org_id, limit, offset,
    )


@router.get("/count")
async def insight_count(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Return the user's total insight count (for badge display)."""
    store = _get_store(request)
    count = await asyncio.to_thread(store.get_insight_count, user.id, user.org_id)
    return {"count": count}


@router.get("/{insight_id}")
async def get_insight(
    insight_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Get a single insight detail."""
    store = _get_store(request)
    insight = await asyncio.to_thread(store.get_insight, insight_id, user.id)
    if insight is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    return insight


@router.patch("/{insight_id}/bookmark")
async def bookmark_insight(
    insight_id: str,
    body: BookmarkRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Toggle bookmark on an insight."""
    store = _get_store(request)
    ok = await asyncio.to_thread(store.bookmark_insight, insight_id, user.id, body.bookmarked)
    if not ok:
        raise HTTPException(status_code=404, detail="Insight not found")
    return {"status": "ok", "bookmarked": body.bookmarked}


@router.delete("/{insight_id}")
async def delete_insight(
    insight_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Delete an insight."""
    store = _get_store(request)
    ok = await asyncio.to_thread(store.delete_insight, insight_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Insight not found")
    return {"status": "ok"}
