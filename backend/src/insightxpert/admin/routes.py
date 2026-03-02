from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from insightxpert.admin.config_store import (
    delete_org_config,
    read_config,
    set_org_config,
    write_config,
)
from insightxpert.admin.dependencies import (
    AdminContext,
    assert_conversation_in_scope,
    assert_org_in_scope,
    assert_user_in_scope,
    get_admin_context,
    require_super_admin,
)
from insightxpert.admin.models import (
    ClientConfig,
    FeatureToggles,
    GlobalSettingsUpdate,
    OrgBranding,
    OrgConfig,
    ResolvedClientConfig,
)
from insightxpert.auth.conversation_store import PersistentConversationStore
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import Organization, PromptTemplate, User
from insightxpert.auth.permissions import is_admin_user
from insightxpert.auth.models import User as UserModel
from insightxpert.prompts import get_file_content

logger = logging.getLogger("insightxpert.admin")

router = APIRouter()


class PromptUpdateBody(BaseModel):
    content: str = Field(..., min_length=1)
    description: str | None = None
    is_active: bool = True


# --- Admin endpoints (admin only) -------------------------------------------


@router.get("/api/admin/config")
async def get_full_config(
    ctx: AdminContext = Depends(get_admin_context),
):
    if ctx.scoped_org_id is None:
        return ctx.config
    # Org-scoped admin: return only their org, strip global settings
    own_org = ctx.config.organizations.get(ctx.scoped_org_id)
    return ClientConfig(
        admin_domains=[],
        user_org_mappings={},
        organizations={ctx.scoped_org_id: own_org} if own_org else {},
        defaults=ctx.config.defaults,
    )


@router.put("/api/admin/config")
async def update_global_config(
    body: GlobalSettingsUpdate,
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    require_super_admin(ctx)
    config = ctx.config
    if body.admin_domains is not None:
        config.admin_domains = body.admin_domains
    if body.user_org_mappings is not None:
        config.user_org_mappings = body.user_org_mappings
    if body.defaults is not None:
        config.defaults = body.defaults

    engine = request.app.state.auth_engine
    await asyncio.to_thread(write_config, engine, config)
    return config


@router.get("/api/admin/organizations")
async def list_organizations(
    ctx: AdminContext = Depends(get_admin_context),
):
    orgs = ctx.config.organizations.values()
    if ctx.scoped_org_id is not None:
        orgs = [o for o in orgs if o.org_id == ctx.scoped_org_id]
    return {
        "organizations": [
            {"org_id": org.org_id, "org_name": org.org_name}
            for org in orgs
        ]
    }


class CreateOrgRequest(BaseModel):
    org_name: str


@router.post("/api/admin/organizations")
async def create_org(
    body: CreateOrgRequest,
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    require_super_admin(ctx)
    import uuid as _uuid

    engine = request.app.state.auth_engine
    org_id = str(_uuid.uuid4())
    org_config = OrgConfig(
        org_id=org_id,
        org_name=body.org_name,
        features=FeatureToggles(),
        branding=OrgBranding(),
    )
    updated = await asyncio.to_thread(set_org_config, engine, org_id, org_config)
    return updated.organizations[org_id]


@router.get("/api/admin/config/{org_id}")
async def get_org(
    org_id: str,
    ctx: AdminContext = Depends(get_admin_context),
):
    assert_org_in_scope(ctx, org_id)
    org = ctx.config.organizations.get(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.put("/api/admin/config/{org_id}")
async def upsert_org(
    org_id: str,
    body: OrgConfig,
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    assert_org_in_scope(ctx, org_id)
    body.org_id = org_id
    engine = request.app.state.auth_engine
    updated = await asyncio.to_thread(set_org_config, engine, org_id, body)
    return updated.organizations[org_id]


@router.delete("/api/admin/config/{org_id}")
async def delete_org(
    org_id: str,
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    require_super_admin(ctx)
    if org_id not in ctx.config.organizations:
        raise HTTPException(status_code=404, detail="Organization not found")

    engine = request.app.state.auth_engine
    await asyncio.to_thread(delete_org_config, engine, org_id)
    return {"status": "ok"}


# --- RAG management (admin only) ---------------------------------------------


@router.delete("/api/admin/rag/qa-pairs")
async def flush_qa_pairs(
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    """Delete all QA pairs from ChromaDB, keeping DDL, docs, and findings."""
    require_super_admin(ctx)
    rag = request.app.state.rag
    count = rag.flush_qa_pairs()
    logger.info("Admin %s flushed %d QA pairs", ctx.user.email, count)
    return {"status": "ok", "deleted_count": count}


# --- Conversation management (admin only) ------------------------------------


@router.get("/api/admin/users/{user_id}/conversations")
async def list_user_conversations(
    user_id: str,
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    """List all conversations for a specific user (admin view, org-scoped)."""
    assert_user_in_scope(ctx, user_id)
    store: PersistentConversationStore = request.app.state.persistent_conv_store
    convos = await asyncio.to_thread(store.get_conversations, user_id)
    # Org-scoped admins only see conversations belonging to their org
    if ctx.scoped_org_id is not None:
        convos = [c for c in convos if c.get("org_id") == ctx.scoped_org_id]
    return {"conversations": convos}


@router.get("/api/admin/conversations/{conversation_id}")
async def get_admin_conversation(
    conversation_id: str,
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    """Get full conversation detail with messages (admin view, org-scoped)."""
    store: PersistentConversationStore = request.app.state.persistent_conv_store
    convo = await asyncio.to_thread(store.get_conversation_admin, conversation_id)
    if convo is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    assert_conversation_in_scope(ctx, convo)

    messages = [
        {
            "id": m["id"],
            "role": m["role"],
            "content": m["content"],
            "chunks": json.loads(m["chunks_json"]) if m.get("chunks_json") else None,
            "feedback": m.get("feedback"),
            "feedback_comment": m.get("feedback_comment"),
            "input_tokens": m.get("input_tokens"),
            "output_tokens": m.get("output_tokens"),
            "generation_time_ms": m.get("generation_time_ms"),
            "created_at": m["created_at"],
        }
        for m in convo["messages"]
    ]
    return {
        "id": convo["id"],
        "title": convo["title"],
        "is_starred": convo.get("is_starred", False),
        "messages": messages,
        "created_at": convo["created_at"],
        "updated_at": convo["updated_at"],
    }


@router.delete("/api/admin/conversations/{conversation_id}")
async def delete_admin_conversation(
    conversation_id: str,
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    """Delete a single conversation (admin, org-scoped)."""
    store: PersistentConversationStore = request.app.state.persistent_conv_store
    if ctx.scoped_org_id is not None:
        convo = await asyncio.to_thread(store.get_conversation_admin, conversation_id)
        if convo is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        assert_conversation_in_scope(ctx, convo)
    deleted = await asyncio.to_thread(store.delete_conversation_admin, conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    logger.info("Admin %s deleted conversation %s", ctx.user.email, conversation_id)
    return {"status": "ok"}


@router.get("/api/admin/users")
async def list_users_with_stats(
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    """List all users with conversation and message counts."""
    store: PersistentConversationStore = request.app.state.persistent_conv_store
    return {
        "users": await asyncio.to_thread(
            store.get_all_users_with_stats, ctx.scoped_user_ids, ctx.scoped_org_id
        )
    }


@router.delete("/api/admin/conversations/user/{user_id}")
async def delete_user_conversations(
    user_id: str,
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    """Delete all conversations for a specific user (org-scoped)."""
    assert_user_in_scope(ctx, user_id)
    store: PersistentConversationStore = request.app.state.persistent_conv_store
    if ctx.scoped_org_id is not None:
        count = await asyncio.to_thread(
            store.delete_conversations_by_org, user_id, ctx.scoped_org_id
        )
    else:
        count = await asyncio.to_thread(store.delete_user_conversations, user_id)
    logger.info("Admin %s deleted %d conversations for user %s", ctx.user.email, count, user_id)
    return {"status": "ok", "deleted_count": count}


@router.delete("/api/admin/conversations")
async def delete_all_conversations(
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    """Delete ALL conversations (super admin) or org conversations (org admin)."""
    store: PersistentConversationStore = request.app.state.persistent_conv_store
    if ctx.scoped_org_id is not None:
        count = await asyncio.to_thread(
            store.delete_conversations_by_org_all, ctx.scoped_org_id
        )
        logger.info(
            "Org admin %s deleted %d conversations for org %s",
            ctx.user.email, count, ctx.scoped_org_id,
        )
    else:
        count = await asyncio.to_thread(store.delete_all_conversations)
        logger.info("Admin %s deleted ALL conversations (%d total)", ctx.user.email, count)
    return {"status": "ok", "deleted_count": count}


# --- Prompt management (admin only) -------------------------------------------


def _prompt_to_dict(p: PromptTemplate) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "content": p.content,
        "description": p.description,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("/api/admin/prompts")
async def list_prompts(
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    """List all prompt templates."""
    require_super_admin(ctx)
    def _query():
        engine = request.app.state.auth_engine
        with Session(engine) as session:
            prompts = session.query(PromptTemplate).order_by(PromptTemplate.name).all()
            return {"prompts": [_prompt_to_dict(p) for p in prompts]}
    return await asyncio.to_thread(_query)


_PROMPT_NAME = Path(..., pattern=r"^[a-z][a-z0-9_]{0,99}$", description="Prompt template name")


@router.get("/api/admin/prompts/{name}")
async def get_prompt(
    name: str = _PROMPT_NAME,
    *,
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    """Get a specific prompt template by name."""
    require_super_admin(ctx)
    def _query():
        engine = request.app.state.auth_engine
        with Session(engine) as session:
            prompt = session.query(PromptTemplate).filter(PromptTemplate.name == name).first()
            if not prompt:
                raise HTTPException(status_code=404, detail="Prompt not found")
            return _prompt_to_dict(prompt)
    return await asyncio.to_thread(_query)


@router.put("/api/admin/prompts/{name}")
async def upsert_prompt(
    name: str = _PROMPT_NAME,
    *,
    body: PromptUpdateBody,
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    """Create or update a prompt template."""
    require_super_admin(ctx)
    def _query():
        engine = request.app.state.auth_engine
        with Session(engine) as session:
            prompt = session.query(PromptTemplate).filter(PromptTemplate.name == name).first()
            if prompt:
                prompt.content = body.content
                prompt.description = body.description
                prompt.is_active = body.is_active
            else:
                from insightxpert.auth.models import _uuid, _utcnow

                prompt = PromptTemplate(
                    id=_uuid(),
                    name=name,
                    content=body.content,
                    description=body.description,
                    is_active=body.is_active,
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                )
                session.add(prompt)
            session.commit()
            logger.info("Admin %s upserted prompt '%s'", ctx.user.email, name)
            return {"status": "ok", "name": name}
    return await asyncio.to_thread(_query)


@router.delete("/api/admin/prompts/{name}")
async def delete_prompt(
    name: str = _PROMPT_NAME,
    *,
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    """Delete a prompt template (reverts to file fallback)."""
    require_super_admin(ctx)
    def _query():
        engine = request.app.state.auth_engine
        with Session(engine) as session:
            prompt = session.query(PromptTemplate).filter(PromptTemplate.name == name).first()
            if not prompt:
                raise HTTPException(status_code=404, detail="Prompt not found")
            session.delete(prompt)
            session.commit()
            logger.info("Admin %s deleted prompt '%s'", ctx.user.email, name)
            return {"status": "ok", "name": name}
    return await asyncio.to_thread(_query)


@router.post("/api/admin/prompts/{name}/reset")
async def reset_prompt(
    name: str = _PROMPT_NAME,
    *,
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    """Reset a prompt template to its file-based default."""
    require_super_admin(ctx)
    template_file = f"{name}.j2"
    try:
        file_content = get_file_content(template_file)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No file template found for '{name}'")

    def _query():
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
    return await asyncio.to_thread(_query)


# --- Public endpoint (any authenticated user) --------------------------------


def _resolve_config_sync(
    engine, user_id: str, is_admin: bool, config: ClientConfig,
) -> ResolvedClientConfig:
    """Synchronous helper — resolves client config from the DB."""
    if is_admin:
        with Session(engine) as session:
            db_user = session.get(UserModel, user_id)
            admin_org_id = db_user.org_id if db_user else None

            branding = config.defaults.branding
            if admin_org_id:
                org = session.get(Organization, admin_org_id)
                if org:
                    branding = OrgBranding.model_validate(json.loads(org.branding_json))

            all_features = FeatureToggles(
                sql_executor=True,
                model_switching=True,
                rag_training=True,
                rag_retrieval=True,
                chart_rendering=True,
                conversation_export=True,
                agent_process_sidebar=True,
                clarification_enabled=True,
                stats_context_injection=True,
            )
            admin_config = OrgConfig(
                org_id=admin_org_id or "admin",
                org_name="Admin",
                features=all_features,
                branding=branding,
            )
        return ResolvedClientConfig(config=admin_config, is_admin=True, org_id=admin_org_id)

    with Session(engine) as session:
        db_user = session.get(UserModel, user_id)
        if db_user and db_user.org_id:
            org = session.get(Organization, db_user.org_id)
            if org:
                org_config = OrgConfig(
                    org_id=org.id,
                    org_name=org.name,
                    features=FeatureToggles.model_validate(json.loads(org.features_json)),
                    branding=OrgBranding.model_validate(json.loads(org.branding_json)),
                )
                return ResolvedClientConfig(config=org_config, is_admin=False, org_id=org.id)

    default_org = OrgConfig(
        org_id="default",
        org_name="Default",
        features=config.defaults.features,
        branding=config.defaults.branding,
    )
    return ResolvedClientConfig(config=default_org, is_admin=False, org_id=None)


@router.get("/api/client-config")
async def resolve_client_config(
    request: Request,
    user: User = Depends(get_current_user),
):
    engine = request.app.state.auth_engine
    config = await asyncio.to_thread(read_config, engine)
    admin = is_admin_user(user, config.admin_domains)
    return await asyncio.to_thread(_resolve_config_sync, engine, user.id, admin, config)
