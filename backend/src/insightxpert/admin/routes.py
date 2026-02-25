from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status

from insightxpert.admin.config_store import (
    delete_org_config,
    read_config,
    set_org_config,
    write_config,
)
from insightxpert.admin.models import (
    ClientConfig,
    OrgConfig,
    ResolvedClientConfig,
)
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import User

logger = logging.getLogger("insightxpert.admin")

router = APIRouter()


def _config_path(request: Request) -> Path:
    return request.app.state.config_path


def is_admin_user(user: User, config: ClientConfig) -> bool:
    if user.is_admin:
        return True
    domain = user.email.split("@")[1].lower()
    return domain in [d.lower() for d in config.admin_domains]


def _require_admin(user: User, config: ClientConfig) -> None:
    if not is_admin_user(user, config):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


class _AdminContext:
    """Bundles admin-verified config + user so endpoints don't re-resolve the user."""
    __slots__ = ("config", "user")

    def __init__(self, config: ClientConfig, user: User) -> None:
        self.config = config
        self.user = user


def _get_admin_context(
    request: Request,
    user: User = Depends(get_current_user),
) -> _AdminContext:
    path = _config_path(request)
    config = read_config(path)
    _require_admin(user, config)
    return _AdminContext(config, user)


# --- Admin endpoints (admin only) -------------------------------------------


@router.get("/api/admin/config")
async def get_full_config(
    ctx: _AdminContext = Depends(_get_admin_context),
):
    return ctx.config


@router.put("/api/admin/config")
async def update_global_config(
    body: dict,
    request: Request,
    ctx: _AdminContext = Depends(_get_admin_context),
):
    config = ctx.config
    if "admin_domains" in body:
        config.admin_domains = body["admin_domains"]
    if "user_org_mappings" in body:
        from insightxpert.admin.models import UserOrgMapping

        config.user_org_mappings = [
            UserOrgMapping.model_validate(m) for m in body["user_org_mappings"]
        ]
    if "defaults" in body:
        from insightxpert.admin.models import DefaultConfig

        config.defaults = DefaultConfig.model_validate(body["defaults"])

    write_config(_config_path(request), config)
    return config


@router.get("/api/admin/organizations")
async def list_organizations(
    ctx: _AdminContext = Depends(_get_admin_context),
):
    return {
        "organizations": [
            {"org_id": org.org_id, "org_name": org.org_name}
            for org in ctx.config.organizations.values()
        ]
    }


@router.get("/api/admin/config/{org_id}")
async def get_org(
    org_id: str,
    ctx: _AdminContext = Depends(_get_admin_context),
):
    org = ctx.config.organizations.get(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.put("/api/admin/config/{org_id}")
async def upsert_org(
    org_id: str,
    body: OrgConfig,
    request: Request,
    _ctx: _AdminContext = Depends(_get_admin_context),
):
    body.org_id = org_id
    updated = set_org_config(_config_path(request), org_id, body)
    return updated.organizations[org_id]


@router.delete("/api/admin/config/{org_id}")
async def delete_org(
    org_id: str,
    request: Request,
    ctx: _AdminContext = Depends(_get_admin_context),
):
    if org_id not in ctx.config.organizations:
        raise HTTPException(status_code=404, detail="Organization not found")

    delete_org_config(_config_path(request), org_id)
    return {"status": "ok"}


# --- RAG management (admin only) ---------------------------------------------


@router.delete("/api/admin/rag/qa-pairs")
async def flush_qa_pairs(
    request: Request,
    ctx: _AdminContext = Depends(_get_admin_context),
):
    """Delete all QA pairs from ChromaDB, keeping DDL, docs, and findings."""
    rag = request.app.state.rag
    count = rag.flush_qa_pairs()
    logger.info("Admin %s flushed %d QA pairs", ctx.user.email, count)
    return {"status": "ok", "deleted_count": count}


# --- Public endpoint (any authenticated user) --------------------------------


@router.get("/api/client-config")
async def resolve_client_config(
    request: Request,
    user: User = Depends(get_current_user),
):
    path = _config_path(request)
    config = read_config(path)
    admin = is_admin_user(user, config)

    # Admins get null config (show everything)
    if admin:
        return ResolvedClientConfig(config=None, is_admin=True, org_id=None)

    # Check user-org mapping
    email_lower = user.email.lower()
    for mapping in config.user_org_mappings:
        if mapping.email.lower() == email_lower:
            org = config.organizations.get(mapping.org_id)
            if org:
                return ResolvedClientConfig(
                    config=org, is_admin=False, org_id=mapping.org_id
                )

    # Default config
    default_org = OrgConfig(
        org_id="default",
        org_name="Default",
        features=config.defaults.features,
        branding=config.defaults.branding,
    )
    return ResolvedClientConfig(config=default_org, is_admin=False, org_id=None)
