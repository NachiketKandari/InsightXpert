from __future__ import annotations

import logging

from insightxpert.auth.models import User

logger = logging.getLogger("insightxpert.auth")


def is_admin_user(user: User, admin_domains: list[str]) -> bool:
    """Check if user is admin via is_admin flag or email domain allowlist."""
    if user.is_admin:
        return True
    try:
        domain = user.email.split("@")[1].lower()
        return domain in [d.lower() for d in admin_domains]
    except (IndexError, AttributeError):
        logger.warning("User %s has malformed email: %s", user.id, user.email)
        return False
