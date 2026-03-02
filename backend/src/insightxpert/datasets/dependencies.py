"""FastAPI dependencies for the datasets module."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi import Depends, Request

from insightxpert.admin.config_store import read_config
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import User
from insightxpert.auth.permissions import is_admin_user


@dataclass
class ResolvedUser:
    user: User
    is_admin: bool
    is_super_admin: bool  # admin with no org


async def resolve_user_roles(
    request: Request,
    user: User = Depends(get_current_user),
) -> ResolvedUser:
    """Resolve the authenticated user's admin status in a single DB call."""
    config = await asyncio.to_thread(read_config, request.app.state.auth_engine)
    is_admin = is_admin_user(user, config.admin_domains)
    return ResolvedUser(
        user=user,
        is_admin=is_admin,
        is_super_admin=is_admin and user.org_id is None,
    )
