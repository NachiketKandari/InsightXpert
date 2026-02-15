"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Save, Trash2, Plus } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiFetch } from "@/lib/api";
import { FeatureTogglesEditor } from "@/components/admin/feature-toggles";
import { BrandingEditor } from "@/components/admin/branding-editor";
import { UserOrgMappingsEditor } from "@/components/admin/user-org-mappings";
import { AdminDomainEditor } from "@/components/admin/admin-domain-editor";
import type {
  ClientConfig,
  OrgConfig,
  FeatureToggles,
  OrgBranding,
} from "@/types/admin";

const DEFAULT_FEATURES: FeatureToggles = {
  sql_executor: true,
  model_switching: true,
  rag_training: true,
  chart_rendering: true,
  conversation_export: true,
  agent_process_sidebar: true,
};

const DEFAULT_BRANDING: OrgBranding = {
  display_name: null,
  logo_url: null,
  theme: null,
};

export default function AdminPage() {
  const [fullConfig, setFullConfig] = useState<ClientConfig | null>(null);
  const [selectedOrgId, setSelectedOrgId] = useState<string>("");
  const [editingConfig, setEditingConfig] = useState<OrgConfig | null>(null);
  const [newOrgId, setNewOrgId] = useState("");
  const [newOrgName, setNewOrgName] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  const loadConfig = useCallback(async () => {
    try {
      const res = await apiFetch("/api/admin/config");
      if (res.ok) {
        const data = await res.json();
        setFullConfig(data);
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  // When org selection changes, load its config
  useEffect(() => {
    if (!fullConfig || !selectedOrgId) {
      setEditingConfig(null);
      return;
    }
    const org = fullConfig.organizations[selectedOrgId];
    if (org) {
      setEditingConfig({ ...org });
    } else {
      setEditingConfig(null);
    }
  }, [selectedOrgId, fullConfig]);

  const showMessage = (type: "success" | "error", text: string) => {
    setSaveMessage({ type, text });
    setTimeout(() => setSaveMessage(null), 3000);
  };

  const saveOrgConfig = async () => {
    if (!editingConfig || !selectedOrgId) return;
    setIsSaving(true);
    try {
      const res = await apiFetch(`/api/admin/config/${selectedOrgId}`, {
        method: "PUT",
        body: JSON.stringify(editingConfig),
      });
      if (res.ok) {
        showMessage("success", "Organization config saved");
        await loadConfig();
      } else {
        showMessage("error", "Failed to save");
      }
    } catch {
      showMessage("error", "Network error");
    }
    setIsSaving(false);
  };

  const deleteOrg = async () => {
    if (!selectedOrgId) return;
    if (!confirm(`Delete organization "${selectedOrgId}"?`)) return;
    setIsSaving(true);
    try {
      const res = await apiFetch(`/api/admin/config/${selectedOrgId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setSelectedOrgId("");
        setEditingConfig(null);
        showMessage("success", "Organization deleted");
        await loadConfig();
      } else {
        showMessage("error", "Failed to delete");
      }
    } catch {
      showMessage("error", "Network error");
    }
    setIsSaving(false);
  };

  const createOrg = async () => {
    const id = newOrgId.trim();
    const name = newOrgName.trim();
    if (!id || !name) return;

    const org: OrgConfig = {
      org_id: id,
      org_name: name,
      features: { ...DEFAULT_FEATURES },
      branding: { ...DEFAULT_BRANDING },
    };

    setIsSaving(true);
    try {
      const res = await apiFetch(`/api/admin/config/${id}`, {
        method: "PUT",
        body: JSON.stringify(org),
      });
      if (res.ok) {
        setNewOrgId("");
        setNewOrgName("");
        showMessage("success", "Organization created");
        await loadConfig();
        setSelectedOrgId(id);
      } else {
        showMessage("error", "Failed to create");
      }
    } catch {
      showMessage("error", "Network error");
    }
    setIsSaving(false);
  };

  const saveGlobalSettings = async () => {
    if (!fullConfig) return;
    setIsSaving(true);
    try {
      const res = await apiFetch("/api/admin/config", {
        method: "PUT",
        body: JSON.stringify({
          admin_domains: fullConfig.admin_domains,
          user_org_mappings: fullConfig.user_org_mappings,
          defaults: fullConfig.defaults,
        }),
      });
      if (res.ok) {
        showMessage("success", "Global settings saved");
        await loadConfig();
      } else {
        showMessage("error", "Failed to save");
      }
    } catch {
      showMessage("error", "Network error");
    }
    setIsSaving(false);
  };

  if (!fullConfig) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  const orgList = Object.values(fullConfig.organizations);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-10 glass border-b border-border px-4 py-3 sm:px-6">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/">
              <Button variant="ghost" size="icon" className="size-9">
                <ArrowLeft className="size-4" />
              </Button>
            </Link>
            <h1 className="text-lg font-semibold">Admin Panel</h1>
          </div>
          {saveMessage && (
            <span
              className={`text-sm ${
                saveMessage.type === "success"
                  ? "text-green-600 dark:text-green-400"
                  : "text-red-600 dark:text-red-400"
              }`}
            >
              {saveMessage.text}
            </span>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        <Tabs defaultValue="organizations" className="space-y-6">
          <TabsList>
            <TabsTrigger value="organizations">Organizations</TabsTrigger>
            <TabsTrigger value="global">Global Settings</TabsTrigger>
          </TabsList>

          {/* Organizations Tab */}
          <TabsContent value="organizations" className="space-y-6">
            {/* Create new org */}
            <div className="rounded-lg border border-border p-4 space-y-3">
              <h3 className="text-sm font-medium">Create Organization</h3>
              <div className="flex items-end gap-2">
                <div className="space-y-1">
                  <Label htmlFor="new-org-id" className="text-xs">
                    ID
                  </Label>
                  <Input
                    id="new-org-id"
                    placeholder="acme"
                    value={newOrgId}
                    onChange={(e) => setNewOrgId(e.target.value)}
                    className="w-32"
                  />
                </div>
                <div className="flex-1 space-y-1">
                  <Label htmlFor="new-org-name" className="text-xs">
                    Name
                  </Label>
                  <Input
                    id="new-org-name"
                    placeholder="Acme Corp"
                    value={newOrgName}
                    onChange={(e) => setNewOrgName(e.target.value)}
                  />
                </div>
                <Button
                  onClick={createOrg}
                  disabled={!newOrgId.trim() || !newOrgName.trim() || isSaving}
                >
                  <Plus className="size-4 mr-1" />
                  Create
                </Button>
              </div>
            </div>

            {/* Org selector + editor */}
            {orgList.length > 0 && (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <Select
                    value={selectedOrgId}
                    onValueChange={setSelectedOrgId}
                  >
                    <SelectTrigger className="w-64">
                      <SelectValue placeholder="Select organization" />
                    </SelectTrigger>
                    <SelectContent>
                      {orgList.map((org) => (
                        <SelectItem key={org.org_id} value={org.org_id}>
                          {org.org_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {selectedOrgId && editingConfig && (
                    <div className="flex items-center gap-2">
                      <Button
                        onClick={saveOrgConfig}
                        disabled={isSaving}
                      >
                        <Save className="size-4 mr-1" />
                        Save
                      </Button>
                      <Button
                        variant="destructive"
                        onClick={deleteOrg}
                        disabled={isSaving}
                      >
                        <Trash2 className="size-4 mr-1" />
                        Delete
                      </Button>
                    </div>
                  )}
                </div>

                {editingConfig && (
                  <Tabs defaultValue="features" className="space-y-4">
                    <TabsList>
                      <TabsTrigger value="features">Features</TabsTrigger>
                      <TabsTrigger value="branding">Branding</TabsTrigger>
                    </TabsList>
                    <TabsContent value="features">
                      <FeatureTogglesEditor
                        features={editingConfig.features}
                        onChange={(features) =>
                          setEditingConfig({ ...editingConfig, features })
                        }
                      />
                    </TabsContent>
                    <TabsContent value="branding">
                      <BrandingEditor
                        branding={editingConfig.branding}
                        onChange={(branding) =>
                          setEditingConfig({ ...editingConfig, branding })
                        }
                      />
                    </TabsContent>
                  </Tabs>
                )}
              </div>
            )}
          </TabsContent>

          {/* Global Settings Tab */}
          <TabsContent value="global" className="space-y-6">
            <AdminDomainEditor
              domains={fullConfig.admin_domains}
              onChange={(admin_domains) =>
                setFullConfig({ ...fullConfig, admin_domains })
              }
            />

            <UserOrgMappingsEditor
              mappings={fullConfig.user_org_mappings}
              organizations={fullConfig.organizations}
              onChange={(user_org_mappings) =>
                setFullConfig({ ...fullConfig, user_org_mappings })
              }
            />

            <Button onClick={saveGlobalSettings} disabled={isSaving}>
              <Save className="size-4 mr-1" />
              Save Global Settings
            </Button>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
