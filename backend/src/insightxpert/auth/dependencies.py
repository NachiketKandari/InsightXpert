from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Generator

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from insightxpert.auth.models import User
from insightxpert.auth.permissions import is_admin_user
from insightxpert.auth.security import decode_access_token

logger = logging.getLogger("insightxpert.auth")


def get_db_session(request: Request) -> Generator[Session, None, None]:
    engine = request.app.state.auth_engine
    with Session(engine) as session:
        yield session


def _fetch_user(engine, user_id: str) -> User | None:
    with Session(engine) as session:
        user = session.get(User, user_id)
        if user is None:
            return None
        session.expunge(user)
        return user


def _update_last_active(engine, user_id: str) -> None:
    try:
        with Session(engine) as session:
            user = session.get(User, user_id)
            if user:
                user.last_active = datetime.now(timezone.utc)
                session.commit()
    except Exception as e:
        logger.debug("last_active update failed: %s", e)



async def get_current_user(request: Request) -> User:
    token = request.cookies.get("__session")
    if not token:
        # Fall back to Authorization: Bearer <token> header (used by SSE
        # requests that go directly to Cloud Run, bypassing the CDN proxy).
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    settings = request.app.state.settings
    payload = decode_access_token(token, settings.secret_key)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    engine = request.app.state.auth_engine
    user = await asyncio.to_thread(_fetch_user, engine, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    asyncio.create_task(asyncio.to_thread(_update_last_active, engine, user_id))
    return user


def require_admin(user: User, admin_domains: list[str] | None = None) -> None:
    """Raise 403 if user is not an admin. Respects admin_domains allowlist when provided."""
    if not is_admin_user(user, admin_domains or []):
        raise HTTPException(status_code=403, detail="Admin access required")
