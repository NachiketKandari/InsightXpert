from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from insightxpert.api.models import LoginRequest, UserResponse
from insightxpert.auth.dependencies import get_current_user, get_db_session
from insightxpert.auth.models import User
from insightxpert.auth.security import create_access_token, verify_password

logger = logging.getLogger("insightxpert.auth")

router = APIRouter(prefix="/api/auth")


@router.post("/login", response_model=UserResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
):
    user = db.query(User).filter(User.email == body.email).first()
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

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )

    logger.info("User logged in: %s", user.email)
    return UserResponse(id=user.id, email=user.email)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return UserResponse(id=user.id, email=user.email)
