from __future__ import annotations

from pydantic import BaseModel


class FeatureToggles(BaseModel):
    sql_executor: bool = True
    model_switching: bool = True
    rag_training: bool = True
    chart_rendering: bool = True
    conversation_export: bool = True
    agent_process_sidebar: bool = True
    clarification_enabled: bool = False
    stats_context_injection: bool = False


class OrgBranding(BaseModel):
    display_name: str | None = None
    logo_url: str | None = None
    theme: dict[str, str] | None = None  # CSS variable overrides
    color_mode: str | None = None  # "dark" | "light" | None (user preference)


class OrgConfig(BaseModel):
    org_id: str
    org_name: str
    features: FeatureToggles = FeatureToggles()
    branding: OrgBranding = OrgBranding()


class UserOrgMapping(BaseModel):
    email: str
    org_id: str


class DefaultConfig(BaseModel):
    features: FeatureToggles = FeatureToggles()
    branding: OrgBranding = OrgBranding()


class ClientConfig(BaseModel):
    admin_domains: list[str] = ["insightxpert.ai"]
    user_org_mappings: list[UserOrgMapping] = []
    organizations: dict[str, OrgConfig] = {}
    defaults: DefaultConfig = DefaultConfig()


class ResolvedClientConfig(BaseModel):
    config: OrgConfig | None = None
    is_admin: bool = False
    org_id: str | None = None
