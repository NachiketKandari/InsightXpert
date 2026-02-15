export interface FeatureToggles {
  sql_executor: boolean;
  model_switching: boolean;
  rag_training: boolean;
  chart_rendering: boolean;
  conversation_export: boolean;
  agent_process_sidebar: boolean;
}

export interface OrgBranding {
  display_name: string | null;
  logo_url: string | null;
  theme: Record<string, string> | null;
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

export interface ResolvedClientConfig {
  config: OrgConfig | null;
  is_admin: boolean;
  org_id: string | null;
}
