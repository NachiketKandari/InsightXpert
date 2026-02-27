from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Generator

from fastapi import HTTPException, Request, status
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from insightxpert.auth.models import User
from insightxpert.auth.security import decode_access_token

logger = logging.getLogger("insightxpert.auth")

_read_only_warned = False


def get_db_session(request: Request) -> Generator[Session, None, None]:
    engine = request.app.state.auth_engine
    with Session(engine) as session:
        yield session


def _fetch_user(engine, user_id: str) -> User | None:
    """Fetch user and update last_active (sync, meant to run in a thread)."""
    global _read_only_warned
    with Session(engine) as session:
        user = session.get(User, user_id)
        if user is None or not user.is_active:
            return None
        if not _read_only_warned:
            user.last_active = datetime.now(timezone.utc)
            try:
                session.commit()
                session.refresh(user)
            except OperationalError:
                logger.warning("Database is read-only; last_active updates will be skipped")
                _read_only_warned = True
                session.rollback()
                session.refresh(user)
        session.expunge(user)
        return user


async def get_current_user(request: Request) -> User:
    token = request.cookies.get("__session")
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
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user
