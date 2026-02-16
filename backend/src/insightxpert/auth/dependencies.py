from __future__ import annotations

from datetime import datetime, timezone
from typing import Generator

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from insightxpert.auth.models import User
from insightxpert.auth.security import decode_access_token

def get_db_session(request: Request) -> Generator[Session, None, None]:
    engine = request.app.state.auth_engine
    with Session(engine) as session:
        yield session


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
    with Session(engine) as session:
        user = session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        user.last_active = datetime.now(timezone.utc)
        session.commit()
        # Detach from session so it can be used outside
        session.expunge(user)
        return user
