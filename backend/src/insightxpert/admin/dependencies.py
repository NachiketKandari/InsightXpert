"""Shared admin plumbing — context, scope resolution, and FastAPI dependencies.

Consolidates admin helpers previously duplicated across admin/routes.py,
automations/routes.py, datasets/routes.py, and insights/routes.py.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

logger = logging.getLogger("insightxpert.admin")

from insightxpert.admin.config_store import read_config
from insightxpert.admin.models import ClientConfig
from insightxpert.auth.dependencies import get_current_user, require_admin
from insightxpert.auth.models import User
from insightxpert.auth.models import User as UserModel


class AdminContext:
    """Bundles admin-verified config + user so endpoints don't re-resolve the user."""

    __slots__ = ("config", "user", "scoped_user_ids", "scoped_org_id")

    def __init__(
        self,
        config: ClientConfig,
        user: User,
        scoped_user_ids: set[str] | None,
        scoped_org_id: str | None,
    ) -> None:
        self.config = config
        self.user = user
        # None → super admin (sees everything); set → org-scoped admin
        self.scoped_user_ids = scoped_user_ids
        # The org_id this admin is scoped to (None for super admins)
        self.scoped_org_id = scoped_org_id


# ---------------------------------------------------------------------------
# Scope resolution
# ---------------------------------------------------------------------------


def _resolve_admin_scope(user: User, engine) -> tuple[set[str] | None, str | None]:
    """Determine the set of user IDs an org-scoped admin may access.

    Uses ``users.org_id`` FK directly — no need to scan email-based mappings.
    Returns (None, None) for super admins (unrestricted) or (user_ids, org_id)
    for org-scoped admins.
    """
    with Session(engine) as session:
        db_user = session.get(UserModel, user.id)
        if db_user is None:
            logger.warning("Admin scope: user %s not found in DB", user.id)
            raise HTTPException(status_code=403, detail="User not found")
        logger.debug(
            "Admin scope: user=%s email=%s org_id=%s is_admin=%s",
            db_user.id, db_user.email, db_user.org_id, db_user.is_admin,
        )
        if db_user.org_id is None:
            return None, None  # super admin — unrestricted
        admin_org_id = db_user.org_id
        rows = session.query(UserModel.id).filter(UserModel.org_id == admin_org_id).all()
        user_ids = {r.id for r in rows}
        logger.debug("Admin scope: org=%s, scoped to %d users", admin_org_id, len(user_ids))
        return user_ids, admin_org_id


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def assert_user_in_scope(ctx: AdminContext, user_id: str) -> None:
    """Raise 403 if *user_id* is outside the org admin's scope."""
    if ctx.scoped_user_ids is not None and user_id not in ctx.scoped_user_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not in your organization",
        )


def assert_conversation_in_scope(ctx: AdminContext, convo: dict) -> None:
    """Raise 403 if the conversation's org doesn't match the admin's org."""
    if ctx.scoped_org_id is not None and convo.get("org_id") != ctx.scoped_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conversation not in your organization",
        )


def require_super_admin(ctx: AdminContext) -> None:
    """Raise 403 if the admin is org-scoped (not a super admin)."""
    if ctx.scoped_org_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation requires super-admin access",
        )


def assert_org_in_scope(ctx: AdminContext, org_id: str) -> None:
    """Raise 403 if *org_id* is outside the org admin's scope."""
    if ctx.scoped_org_id is not None and org_id != ctx.scoped_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization not in your scope",
        )


def assert_resource_in_scope(resource: dict, user: User, label: str = "Resource") -> None:
    """Raise 403 if an org-scoped admin tries to access a resource outside their org."""
    if user.org_id is not None and resource.get("org_id") != user.org_id:
        raise HTTPException(status_code=403, detail=f"{label} not in your organization")


def require_super_admin_for_datasets(user: User) -> None:
    """Raise 403 if the admin is org-scoped (not a super admin)."""
    if user.org_id is not None:
        raise HTTPException(
            status_code=403,
            detail="Dataset management requires super-admin access",
        )


# ---------------------------------------------------------------------------
# Admin domains helper
# ---------------------------------------------------------------------------


def _get_admin_domains(request: Request) -> list[str]:
    """Read admin_domains from the persisted config."""
    engine = request.app.state.auth_engine
    config = read_config(engine)
    return config.admin_domains


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_admin_context(
    request: Request,
    user: User = Depends(get_current_user),
) -> AdminContext:
    """FastAPI dependency: verify admin and return scoped context."""
    engine = request.app.state.auth_engine
    config = await asyncio.to_thread(read_config, engine)
    require_admin(user, config.admin_domains)
    scoped_ids, scoped_org_id = await asyncio.to_thread(_resolve_admin_scope, user, engine)
    return AdminContext(config, user, scoped_ids, scoped_org_id)


async def require_admin_user(
    request: Request,
    user: User = Depends(get_current_user),
) -> User:
    """FastAPI dependency: verify admin and return user."""
    admin_domains = await asyncio.to_thread(_get_admin_domains, request)
    require_admin(user, admin_domains)
    return user


async def require_super_admin_user(
    request: Request,
    user: User = Depends(get_current_user),
) -> User:
    """FastAPI dependency: verify super-admin and return user."""
    admin_domains = await asyncio.to_thread(_get_admin_domains, request)
    require_admin(user, admin_domains)
    require_super_admin_for_datasets(user)
    return user
