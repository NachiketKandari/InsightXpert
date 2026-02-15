from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from insightxpert.auth.models import User
from insightxpert.auth.security import hash_password

logger = logging.getLogger("insightxpert.auth")

ADMIN_EMAIL = "admin@insightxpert.ai"
ADMIN_PASSWORD = "admin123"


def seed_admin(engine) -> None:
    with Session(engine) as session:
        existing = session.query(User).filter(User.email == ADMIN_EMAIL).first()
        if existing:
            logger.info("Admin user already exists: %s", ADMIN_EMAIL)
            return

        user = User(
            email=ADMIN_EMAIL,
            hashed_password=hash_password(ADMIN_PASSWORD),
            is_admin=True,
        )
        session.add(user)
        session.commit()
        logger.info("Admin user created: %s", ADMIN_EMAIL)
