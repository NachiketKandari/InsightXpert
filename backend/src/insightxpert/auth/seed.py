from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from insightxpert.auth.models import User
from insightxpert.auth.security import hash_password
from insightxpert.config import Settings

logger = logging.getLogger("insightxpert.auth")


def seed_admin(engine, settings: Settings) -> None:
    email = settings.admin_seed_email
    password = settings.admin_seed_password
    with Session(engine) as session:
        existing = session.query(User).filter(User.email == email).first()
        if existing:
            logger.info("Admin user already exists: %s", email)
            return

        user = User(
            email=email,
            hashed_password=hash_password(password),
            is_admin=True,
        )
        session.add(user)
        session.commit()
        logger.info("Admin user created: %s", email)
