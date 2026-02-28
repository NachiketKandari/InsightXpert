from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from insightxpert.api.models import LoginRequest, RegisterRequest, UserResponse
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import User
from insightxpert.auth.security import create_access_token, hash_password, verify_password

logger = logging.getLogger("insightxpert.auth")

router = APIRouter(prefix="/api/auth")


def _cookie_flags(request: Request) -> tuple[bool, str]:
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    origin = request.headers.get("origin", "")
    origin_host = urlparse(origin).hostname if origin else None
    is_cross_site = bool(origin_host) and origin_host != (request.url.hostname or "")
    secure = is_https or is_cross_site
    samesite = "none" if is_cross_site else "lax"
    return secure, samesite


def _find_user_by_email(engine, email: str) -> User | None:
    with Session(engine) as session:
        user = session.query(User).filter(User.email == email).first()
        if user is None:
            return None
        session.expunge(user)
        return user


def _create_user(engine, email: str, hashed: str) -> User:
    """Create a new user with role=user, no org. Returns the detached User."""
    now = datetime.now(timezone.utc)
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        hashed_password=hashed,
        is_active=True,
        is_admin=False,
        org_id=None,
        created_at=now,
        updated_at=now,
    )
    with Session(engine) as session:
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
    return user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
):
    engine = request.app.state.auth_engine

    # Check for existing user
    existing = await asyncio.to_thread(_find_user_by_email, engine, body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # Validate password length
    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )

    hashed = hash_password(body.password)
    user = await asyncio.to_thread(_create_user, engine, body.email, hashed)

    # Auto-login: set session cookie
    settings = request.app.state.settings
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        secret_key=settings.secret_key,
        expire_minutes=settings.access_token_expire_minutes,
    )

    secure, samesite = _cookie_flags(request)
    response.set_cookie(
        key="__session",
        value=token,
        httponly=True,
        samesite=samesite,
        secure=secure,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )

    logger.info("New user registered: %s", user.email)
    return UserResponse(id=user.id, email=user.email, is_admin=user.is_admin)


@router.post("/login", response_model=UserResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
):
    engine = request.app.state.auth_engine
    user = await asyncio.to_thread(_find_user_by_email, engine, body.email)
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    settings = request.app.state.settings
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        secret_key=settings.secret_key,
        expire_minutes=settings.access_token_expire_minutes,
    )

    secure, samesite = _cookie_flags(request)
    response.set_cookie(
        key="__session",
        value=token,
        httponly=True,
        samesite=samesite,
        secure=secure,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )

    logger.info("User logged in: %s", user.email)
    return UserResponse(id=user.id, email=user.email, is_admin=user.is_admin)


@router.post("/logout")
async def logout(request: Request, response: Response):
    secure, samesite = _cookie_flags(request)
    response.delete_cookie(key="__session", path="/", secure=secure, samesite=samesite)
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return UserResponse(id=user.id, email=user.email, is_admin=user.is_admin)
