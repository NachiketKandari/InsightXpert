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
from sqlalchemy.orm import Session

from insightxpert.auth.conversation_store import PersistentConversationStore
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import PromptTemplate, User
from insightxpert.prompts import get_file_content

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


# --- Conversation management (admin only) ------------------------------------


@router.get("/api/admin/users")
async def list_users_with_stats(
    request: Request,
    ctx: _AdminContext = Depends(_get_admin_context),
):
    """List all users with conversation and message counts."""
    store: PersistentConversationStore = request.app.state.persistent_conv_store
    return {"users": store.get_all_users_with_stats()}


@router.delete("/api/admin/conversations/user/{user_id}")
async def delete_user_conversations(
    user_id: str,
    request: Request,
    ctx: _AdminContext = Depends(_get_admin_context),
):
    """Delete all conversations for a specific user."""
    store: PersistentConversationStore = request.app.state.persistent_conv_store
    count = store.delete_user_conversations(user_id)
    logger.info("Admin %s deleted %d conversations for user %s", ctx.user.email, count, user_id)
    return {"status": "ok", "deleted_count": count}


@router.delete("/api/admin/conversations")
async def delete_all_conversations(
    request: Request,
    ctx: _AdminContext = Depends(_get_admin_context),
):
    """Delete ALL conversations across all users."""
    store: PersistentConversationStore = request.app.state.persistent_conv_store
    count = store.delete_all_conversations()
    logger.info("Admin %s deleted ALL conversations (%d total)", ctx.user.email, count)
    return {"status": "ok", "deleted_count": count}


# --- Prompt management (admin only) -------------------------------------------


@router.get("/api/admin/prompts")
async def list_prompts(
    request: Request,
    _ctx: _AdminContext = Depends(_get_admin_context),
):
    """List all prompt templates."""
    engine = request.app.state.auth_engine
    with Session(engine) as session:
        prompts = session.query(PromptTemplate).order_by(PromptTemplate.name).all()
        return {
            "prompts": [
                {
                    "id": p.id,
                    "name": p.name,
                    "content": p.content,
                    "description": p.description,
                    "is_active": p.is_active,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in prompts
            ]
        }


@router.get("/api/admin/prompts/{name}")
async def get_prompt(
    name: str,
    request: Request,
    _ctx: _AdminContext = Depends(_get_admin_context),
):
    """Get a specific prompt template by name."""
    engine = request.app.state.auth_engine
    with Session(engine) as session:
        prompt = session.query(PromptTemplate).filter(PromptTemplate.name == name).first()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        return {
            "id": prompt.id,
            "name": prompt.name,
            "content": prompt.content,
            "description": prompt.description,
            "is_active": prompt.is_active,
            "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
            "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
        }


@router.put("/api/admin/prompts/{name}")
async def upsert_prompt(
    name: str,
    body: dict,
    request: Request,
    ctx: _AdminContext = Depends(_get_admin_context),
):
    """Create or update a prompt template."""
    engine = request.app.state.auth_engine
    with Session(engine) as session:
        prompt = session.query(PromptTemplate).filter(PromptTemplate.name == name).first()
        if prompt:
            prompt.content = body.get("content", prompt.content)
            prompt.description = body.get("description", prompt.description)
            if "is_active" in body:
                prompt.is_active = body["is_active"]
        else:
            from insightxpert.auth.models import _uuid, _utcnow

            prompt = PromptTemplate(
                id=_uuid(),
                name=name,
                content=body.get("content", ""),
                description=body.get("description"),
                is_active=body.get("is_active", True),
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            session.add(prompt)
        session.commit()
        logger.info("Admin %s upserted prompt '%s'", ctx.user.email, name)
        return {"status": "ok", "name": name}


@router.delete("/api/admin/prompts/{name}")
async def delete_prompt(
    name: str,
    request: Request,
    ctx: _AdminContext = Depends(_get_admin_context),
):
    """Delete a prompt template (reverts to file fallback)."""
    engine = request.app.state.auth_engine
    with Session(engine) as session:
        prompt = session.query(PromptTemplate).filter(PromptTemplate.name == name).first()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        session.delete(prompt)
        session.commit()
        logger.info("Admin %s deleted prompt '%s'", ctx.user.email, name)
        return {"status": "ok", "name": name}


@router.post("/api/admin/prompts/{name}/reset")
async def reset_prompt(
    name: str,
    request: Request,
    ctx: _AdminContext = Depends(_get_admin_context),
):
    """Reset a prompt template to its file-based default."""
    template_file = f"{name}.j2"
    try:
        file_content = get_file_content(template_file)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No file template found for '{name}'")

    engine = request.app.state.auth_engine
    with Session(engine) as session:
        prompt = session.query(PromptTemplate).filter(PromptTemplate.name == name).first()
        if prompt:
            prompt.content = file_content
        else:
            from insightxpert.auth.models import _uuid, _utcnow

            prompt = PromptTemplate(
                id=_uuid(),
                name=name,
                content=file_content,
                description=f"System prompt for {name}",
                is_active=True,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            session.add(prompt)
        session.commit()
        logger.info("Admin %s reset prompt '%s' to file default", ctx.user.email, name)
        return {"status": "ok", "name": name}


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
