export interface FeatureToggles {
  sql_executor: boolean;
  model_switching: boolean;
  rag_training: boolean;
  rag_retrieval: boolean;
  chart_rendering: boolean;
  conversation_export: boolean;
  agent_process_sidebar: boolean;
  clarification_enabled: boolean;
  stats_context_injection: boolean;
}

export interface OrgBranding {
  display_name: string | null;
  logo_url: string | null;
  theme: Record<string, string> | null;
  color_mode: "dark" | "light" | null;
}

export interface OrgConfig {
  org_id: string;
  org_name: string;
  features: FeatureToggles;
  branding: OrgBranding;
}

export interface UserOrgMapping {
  email: string;
  org_id: string;
}

export interface DefaultConfig {
  features: FeatureToggles;
  branding: OrgBranding;
}

export interface ClientConfig {
  admin_domains: string[];
  user_org_mappings: UserOrgMapping[];
  organizations: Record<string, OrgConfig>;
  defaults: DefaultConfig;
}

