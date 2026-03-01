"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Save, Trash2, Plus, DatabaseZap, FileText, RotateCcw, ChevronRight, Eye, MessageSquare } from "lucide-react";
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
import { ConversationViewer } from "@/components/admin/conversation-viewer";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { useClientConfig } from "@/hooks/use-client-config";
import type {
  ClientConfig,
  OrgConfig,
} from "@/types/admin";

export default function AdminPage() {
  const [fullConfig, setFullConfig] = useState<ClientConfig | null>(null);
  const [selectedOrgId, setSelectedOrgId] = useState<string>("");
  const [editingConfig, setEditingConfig] = useState<OrgConfig | null>(null);
  const [newOrgName, setNewOrgName] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isFlushing, setIsFlushing] = useState(false);
  const [users, setUsers] = useState<Array<{
    id: string;
    email: string;
    is_active: boolean;
    conversation_count: number;
    message_count: number;
    last_active: string | null;
  }>>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [isDeletingConvos, setIsDeletingConvos] = useState<string | null>(null);
  const [expandedUserId, setExpandedUserId] = useState<string | null>(null);
  const [userConversations, setUserConversations] = useState<Array<{
    id: string;
    title: string;
    is_starred: boolean;
    created_at: string;
    updated_at: string;
    last_message: string | null;
  }>>([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [viewingConversation, setViewingConversation] = useState<any>(null);
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  const [prompts, setPrompts] = useState<Array<{
    id: string;
    name: string;
    content: string;
    description: string | null;
    is_active: boolean;
    created_at: string | null;
    updated_at: string | null;
  }>>([]);
  const [isLoadingPrompts, setIsLoadingPrompts] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState<{
    name: string;
    content: string;
    description: string;
  } | null>(null);
  const [isSavingPrompt, setIsSavingPrompt] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);
  const { confirm, ConfirmDialog } = useConfirm();
  const { orgId } = useClientConfig();
  const isSuperAdmin = !orgId;

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

  const loadUsers = useCallback(async () => {
    setIsLoadingUsers(true);
    try {
      const res = await apiFetch("/api/admin/users");
      if (res.ok) {
        const data = await res.json();
        setUsers(data.users);
      }
    } catch {
      // ignore
    }
    setIsLoadingUsers(false);
  }, []);

  useEffect(() => {
    // Both are async — setState happens in callbacks, not synchronously
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadConfig();
    loadUsers();
  }, [loadConfig, loadUsers]);

  const handleOrgChange = (orgId: string) => {
    setSelectedOrgId(orgId);
    if (!fullConfig || !orgId) {
      setEditingConfig(null);
      return;
    }
    if (orgId === "__all__") {
      setEditingConfig({
        org_id: "__all__",
        org_name: "All (Default)",
        features: { ...fullConfig.defaults.features },
        branding: { ...fullConfig.defaults.branding },
      });
      return;
    }
    const org = fullConfig.organizations[orgId];
    setEditingConfig(org ? { ...org } : null);
  };

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

  const saveDefaultsConfig = async () => {
    if (!editingConfig || !fullConfig) return;
    setIsSaving(true);
    try {
      const updatedDefaults = { ...fullConfig.defaults, features: editingConfig.features };
      const res = await apiFetch("/api/admin/config", {
        method: "PUT",
        body: JSON.stringify({
          admin_domains: fullConfig.admin_domains,
          user_org_mappings: fullConfig.user_org_mappings,
          defaults: updatedDefaults,
        }),
      });
      if (res.ok) {
        showMessage("success", "Default settings saved");
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
    if (!await confirm({ title: "Delete organization", description: `Delete organization "${selectedOrgId}"? This cannot be undone.`, confirmLabel: "Delete", variant: "destructive" })) return;
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
    const name = newOrgName.trim();
    if (!name) return;

    setIsSaving(true);
    try {
      const res = await apiFetch("/api/admin/organizations", {
        method: "POST",
        body: JSON.stringify({ org_name: name }),
      });
      if (res.ok) {
        const created = await res.json();
        setNewOrgName("");
        showMessage("success", "Organization created");
        await loadConfig();
        setSelectedOrgId(created.org_id);
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

  const deleteUserConversations = async (userId: string, email: string) => {
    if (!await confirm({ title: "Delete user conversations", description: `Delete all conversations for ${email}? This cannot be undone.`, confirmLabel: "Delete all", variant: "destructive" })) return;
    setIsDeletingConvos(userId);
    try {
      const res = await apiFetch(`/api/admin/conversations/user/${userId}`, { method: "DELETE" });
      if (res.ok) {
        const data = await res.json();
        showMessage("success", `Deleted ${data.deleted_count} conversation(s) for ${email}`);
        await loadUsers();
      } else {
        showMessage("error", "Failed to delete conversations");
      }
    } catch {
      showMessage("error", "Network error");
    }
    setIsDeletingConvos(null);
  };

  const deleteAllConversations = async () => {
    if (!await confirm({ title: "Delete all conversations", description: "Delete ALL conversations for ALL users? This cannot be undone.", confirmLabel: "Delete everything", variant: "destructive" })) return;
    setIsDeletingConvos("all");
    try {
      const res = await apiFetch("/api/admin/conversations", { method: "DELETE" });
      if (res.ok) {
        const data = await res.json();
        showMessage("success", `Deleted ${data.deleted_count} conversation(s)`);
        await loadUsers();
      } else {
        showMessage("error", "Failed to delete conversations");
      }
    } catch {
      showMessage("error", "Network error");
    }
    setIsDeletingConvos(null);
  };

  const toggleUserExpand = async (userId: string) => {
    if (expandedUserId === userId) {
      setExpandedUserId(null);
      setUserConversations([]);
      return;
    }
    setExpandedUserId(userId);
    setIsLoadingConversations(true);
    try {
      const res = await apiFetch(`/api/admin/users/${userId}/conversations`);
      if (res.ok) {
        const data = await res.json();
        setUserConversations(data.conversations);
      }
    } catch {
      // ignore
    }
    setIsLoadingConversations(false);
  };

  const openConversation = async (conversationId: string) => {
    setIsLoadingConversation(true);
    try {
      const res = await apiFetch(`/api/admin/conversations/${conversationId}`);
      if (res.ok) {
        const data = await res.json();
        setViewingConversation(data);
      } else {
        showMessage("error", "Failed to load conversation");
      }
    } catch {
      showMessage("error", "Network error");
    }
    setIsLoadingConversation(false);
  };

  const deleteConversation = async (conversationId: string, title: string) => {
    if (!await confirm({ title: "Delete conversation", description: `Delete "${title}"? This cannot be undone.`, confirmLabel: "Delete", variant: "destructive" })) return;
    try {
      const res = await apiFetch(`/api/admin/conversations/${conversationId}`, { method: "DELETE" });
      if (res.ok) {
        showMessage("success", "Conversation deleted");
        // Remove from local list
        setUserConversations((prev) => prev.filter((c) => c.id !== conversationId));
        // If viewing this conversation, close modal or navigate
        if (viewingConversation?.id === conversationId) {
          setViewingConversation(null);
        }
        // Refresh user stats
        await loadUsers();
      } else {
        showMessage("error", "Failed to delete conversation");
      }
    } catch {
      showMessage("error", "Network error");
    }
  };

  const flushQaPairs = async () => {
    if (!await confirm({ title: "Clear QA pairs", description: "Remove all learned question-SQL pairs from ChromaDB? DDL schemas, documentation, and findings will be kept. This cannot be undone.", confirmLabel: "Clear", variant: "destructive" })) return;
    setIsFlushing(true);
    try {
      const res = await apiFetch("/api/admin/rag/qa-pairs", { method: "DELETE" });
      if (res.ok) {
        const data = await res.json();
        showMessage("success", `Cleared ${data.deleted_count} QA pair(s)`);
      } else {
        showMessage("error", "Failed to clear QA pairs");
      }
    } catch {
      showMessage("error", "Network error");
    }
    setIsFlushing(false);
  };

  const loadPrompts = useCallback(async () => {
    setIsLoadingPrompts(true);
    try {
      const res = await apiFetch("/api/admin/prompts");
      if (res.ok) {
        const data = await res.json();
        setPrompts(data.prompts);
      }
    } catch {
      // ignore
    }
    setIsLoadingPrompts(false);
  }, []);

  const savePrompt = async () => {
    if (!editingPrompt) return;
    setIsSavingPrompt(true);
    try {
      const res = await apiFetch(`/api/admin/prompts/${editingPrompt.name}`, {
        method: "PUT",
        body: JSON.stringify({
          content: editingPrompt.content,
          description: editingPrompt.description,
        }),
      });
      if (res.ok) {
        showMessage("success", `Prompt "${editingPrompt.name}" saved`);
        setEditingPrompt(null);
        await loadPrompts();
      } else {
        showMessage("error", "Failed to save prompt");
      }
    } catch {
      showMessage("error", "Network error");
    }
    setIsSavingPrompt(false);
  };

  const resetPrompt = async (name: string) => {
    if (!await confirm({ title: "Reset prompt", description: `Reset "${name}" to its file-based default? Current content will be overwritten.`, confirmLabel: "Reset", variant: "default" })) return;
    try {
      const res = await apiFetch(`/api/admin/prompts/${name}/reset`, { method: "POST" });
      if (res.ok) {
        showMessage("success", `Prompt "${name}" reset to default`);
        setEditingPrompt(null);
        await loadPrompts();
      } else {
        showMessage("error", "Failed to reset prompt");
      }
    } catch {
      showMessage("error", "Network error");
    }
  };

  const deletePrompt = async (name: string) => {
    if (!await confirm({ title: "Delete prompt", description: `Delete "${name}"? It will revert to the file-based template.`, confirmLabel: "Delete", variant: "destructive" })) return;
    try {
      const res = await apiFetch(`/api/admin/prompts/${name}`, { method: "DELETE" });
      if (res.ok) {
        showMessage("success", `Prompt "${name}" deleted`);
        setEditingPrompt(null);
        await loadPrompts();
      } else {
        showMessage("error", "Failed to delete prompt");
      }
    } catch {
      showMessage("error", "Network error");
    }
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
            {isSuperAdmin && <TabsTrigger value="global">Global Settings</TabsTrigger>}
            {isSuperAdmin && <TabsTrigger value="rag">RAG Management</TabsTrigger>}
            <TabsTrigger value="conversations">Conversations</TabsTrigger>
            {isSuperAdmin && <TabsTrigger value="prompts">Prompts</TabsTrigger>}
          </TabsList>

          {/* Organizations Tab */}
          <TabsContent value="organizations" className="space-y-6">
            {/* Create new org (super admin only) */}
            {isSuperAdmin && (
            <div className="rounded-lg border border-border p-4 space-y-3">
              <h3 className="text-sm font-medium">Create Organization</h3>
              <div className="flex items-end gap-2">
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
                  disabled={!newOrgName.trim() || isSaving}
                >
                  <Plus className="size-4 mr-1" />
                  Create
                </Button>
              </div>
            </div>
            )}

            {/* Org selector + editor */}
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <Select
                  value={selectedOrgId}
                  onValueChange={handleOrgChange}
                >
                  <SelectTrigger className="w-64">
                    <SelectValue placeholder="Select organization" />
                  </SelectTrigger>
                  <SelectContent>
                    {isSuperAdmin && <SelectItem value="__all__">All (Default)</SelectItem>}
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
                      onClick={selectedOrgId === "__all__" ? saveDefaultsConfig : saveOrgConfig}
                      disabled={isSaving}
                    >
                      <Save className="size-4 mr-1" />
                      {selectedOrgId === "__all__" ? "Save Defaults" : "Save"}
                    </Button>
                    {isSuperAdmin && selectedOrgId !== "__all__" && (
                      <Button
                        variant="destructive"
                        onClick={deleteOrg}
                        disabled={isSaving}
                      >
                        <Trash2 className="size-4 mr-1" />
                        Delete
                      </Button>
                    )}
                  </div>
                )}
              </div>

              {editingConfig && (
                <Tabs defaultValue="features" className="space-y-4">
                  <TabsList>
                    <TabsTrigger value="features">Features</TabsTrigger>
                    {selectedOrgId !== "__all__" && (
                      <TabsTrigger value="branding">Branding</TabsTrigger>
                    )}
                  </TabsList>
                  <TabsContent value="features">
                    <FeatureTogglesEditor
                      features={editingConfig.features}
                      onChange={(features) =>
                        setEditingConfig({ ...editingConfig, features })
                      }
                    />
                  </TabsContent>
                  {selectedOrgId !== "__all__" && (
                    <TabsContent value="branding">
                      <BrandingEditor
                        branding={editingConfig.branding}
                        onChange={(branding) =>
                          setEditingConfig({ ...editingConfig, branding })
                        }
                      />
                    </TabsContent>
                  )}
                </Tabs>
              )}
            </div>
          </TabsContent>

          {/* Global Settings Tab (super admin only) */}
          {isSuperAdmin && <TabsContent value="global" className="space-y-6">
            <AdminDomainEditor
              domains={fullConfig.admin_domains}
              onChange={(admin_domains) =>
                setFullConfig({ ...fullConfig, admin_domains })
              }
            />

            <UserOrgMappingsEditor
              mappings={fullConfig.user_org_mappings}
              organizations={fullConfig.organizations}
              users={users}
              onChange={(user_org_mappings) =>
                setFullConfig({ ...fullConfig, user_org_mappings })
              }
            />

            <Button onClick={saveGlobalSettings} disabled={isSaving}>
              <Save className="size-4 mr-1" />
              Save Global Settings
            </Button>
          </TabsContent>}

          {/* RAG Management Tab (super admin only) */}
          {isSuperAdmin && <TabsContent value="rag" className="space-y-6">
            <div className="rounded-lg border border-border p-4 space-y-3">
              <h3 className="text-sm font-medium">Clear QA Pairs</h3>
              <p className="text-sm text-muted-foreground">
                Remove all learned question–SQL pairs from ChromaDB. DDL schemas,
                documentation, and findings will be kept. The system will
                re-learn from conversations over time.
              </p>
              <Button
                variant="destructive"
                onClick={flushQaPairs}
                disabled={isFlushing}
              >
                <DatabaseZap className="size-4 mr-1" />
                {isFlushing ? "Clearing..." : "Clear QA Pairs"}
              </Button>
            </div>
          </TabsContent>}

          {/* Conversations Tab */}
          <TabsContent value="conversations" className="space-y-6">
            <div className="rounded-lg border border-border p-4 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium">User Conversations</h3>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={loadUsers}
                    disabled={isLoadingUsers}
                  >
                    {isLoadingUsers ? "Loading..." : "Refresh"}
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={deleteAllConversations}
                    disabled={isDeletingConvos !== null}
                  >
                    <Trash2 className="size-4 mr-1" />
                    Delete All
                  </Button>
                </div>
              </div>

              {users.length === 0 && !isLoadingUsers ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  Click &quot;Refresh&quot; to load user data
                </p>
              ) : (
                <div className="space-y-1">
                  {users.map((u) => (
                    <div key={u.id} className="rounded-md border border-border/50">
                      {/* User row */}
                      <div
                        className={`flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-muted/50 transition-colors ${
                          expandedUserId === u.id ? "bg-muted/30" : ""
                        }`}
                        onClick={() => u.conversation_count > 0 && toggleUserExpand(u.id)}
                      >
                        <ChevronRight
                          className={`size-4 text-muted-foreground shrink-0 transition-transform ${
                            expandedUserId === u.id ? "rotate-90" : ""
                          } ${u.conversation_count === 0 ? "invisible" : ""}`}
                        />
                        <div className="flex-1 min-w-0">
                          <span className="text-sm font-medium">{u.email}</span>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-muted-foreground shrink-0">
                          <span className="flex items-center gap-1">
                            <MessageSquare className="size-3" />
                            {u.conversation_count} conv / {u.message_count} msg
                          </span>
                          <span>
                            {u.last_active
                              ? new Date(u.last_active).toLocaleDateString()
                              : "Never"}
                          </span>
                          {u.conversation_count > 0 && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={(e) => {
                                e.stopPropagation();
                                deleteUserConversations(u.id, u.email);
                              }}
                              disabled={isDeletingConvos !== null}
                              className="text-destructive hover:text-destructive h-7 px-2"
                            >
                              <Trash2 className="size-3" />
                            </Button>
                          )}
                        </div>
                      </div>

                      {/* Expanded conversation list */}
                      {expandedUserId === u.id && (
                        <div
                          ref={(el) => {
                            if (!el) return;
                            const rect = el.getBoundingClientRect();
                            const available = window.innerHeight - rect.top - 16;
                            el.style.maxHeight = `${Math.max(available, 120)}px`;
                          }}
                          className="border-t border-border/50 bg-muted/10 px-3 py-2 overflow-y-auto"
                        >
                          {isLoadingConversations ? (
                            <div className="flex items-center justify-center py-4">
                              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-primary" />
                            </div>
                          ) : userConversations.length === 0 ? (
                            <p className="text-xs text-muted-foreground py-3 text-center">
                              No conversations found
                            </p>
                          ) : (
                            <div className="space-y-1">
                              {userConversations.map((conv) => (
                                <div
                                  key={conv.id}
                                  className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-muted/50 cursor-pointer transition-colors"
                                  onClick={() => openConversation(conv.id)}
                                >
                                  <Eye className="size-3.5 text-muted-foreground shrink-0" />
                                  <div className="flex-1 min-w-0">
                                    <p className="text-sm truncate">{conv.title}</p>
                                    {conv.last_message && (
                                      <p className="text-xs text-muted-foreground truncate">
                                        {conv.last_message}
                                      </p>
                                    )}
                                  </div>
                                  <span className="text-xs text-muted-foreground shrink-0">
                                    {new Date(conv.updated_at).toLocaleDateString()}
                                  </span>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      deleteConversation(conv.id, conv.title);
                                    }}
                                    className="text-destructive hover:text-destructive h-7 px-2 shrink-0"
                                  >
                                    <Trash2 className="size-3" />
                                  </Button>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Conversation Viewer Modal */}
            <ConversationViewer
              conversation={viewingConversation}
              open={viewingConversation !== null || isLoadingConversation}
              onOpenChange={(open) => {
                if (!open) {
                  setViewingConversation(null);
                  setIsLoadingConversation(false);
                }
              }}
              currentIndex={
                viewingConversation
                  ? userConversations.findIndex((c) => c.id === viewingConversation.id)
                  : 0
              }
              totalCount={userConversations.length}
              onPrev={() => {
                if (userConversations.length === 0) return;
                const idx = userConversations.findIndex((c) => c.id === viewingConversation?.id);
                const prevIdx = idx <= 0 ? userConversations.length - 1 : idx - 1;
                openConversation(userConversations[prevIdx].id);
              }}
              onNext={() => {
                if (userConversations.length === 0) return;
                const idx = userConversations.findIndex((c) => c.id === viewingConversation?.id);
                const nextIdx = idx >= userConversations.length - 1 ? 0 : idx + 1;
                openConversation(userConversations[nextIdx].id);
              }}
              onDelete={() => {
                if (viewingConversation) {
                  deleteConversation(viewingConversation.id, viewingConversation.title);
                }
              }}
              isLoading={isLoadingConversation}
            />
          </TabsContent>

          {/* Prompts Tab (super admin only) */}
          {isSuperAdmin && <TabsContent value="prompts" className="space-y-6">
            <div className="rounded-lg border border-border p-4 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-medium">System Prompts</h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    Edit the Jinja2 system prompts used by agents. Changes take effect on the next conversation.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={loadPrompts}
                  disabled={isLoadingPrompts}
                >
                  {isLoadingPrompts ? "Loading..." : "Refresh"}
                </Button>
              </div>

              {editingPrompt ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-medium flex items-center gap-2">
                      <FileText className="size-4" />
                      {editingPrompt.name}
                    </h4>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => resetPrompt(editingPrompt.name)}
                      >
                        <RotateCcw className="size-3 mr-1" />
                        Reset to Default
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setEditingPrompt(null)}
                      >
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        onClick={savePrompt}
                        disabled={isSavingPrompt}
                      >
                        <Save className="size-3 mr-1" />
                        {isSavingPrompt ? "Saving..." : "Save"}
                      </Button>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="prompt-desc" className="text-xs">Description</Label>
                    <Input
                      id="prompt-desc"
                      value={editingPrompt.description}
                      onChange={(e) => setEditingPrompt({ ...editingPrompt, description: e.target.value })}
                      placeholder="Brief description of this prompt"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="prompt-content" className="text-xs">
                      Content (Jinja2 template)
                    </Label>
                    <textarea
                      id="prompt-content"
                      value={editingPrompt.content}
                      onChange={(e) => setEditingPrompt({ ...editingPrompt, content: e.target.value })}
                      className="w-full min-h-[400px] rounded-md border border-border bg-background px-3 py-2 text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-ring"
                      spellCheck={false}
                    />
                    <p className="text-xs text-muted-foreground">
                      Available variables: {"{{ ddl }}"}, {"{{ documentation }}"}, {"{{ similar_qa }}"}, {"{{ analyst_sql }}"}, {"{{ results_summary }}"}
                    </p>
                  </div>
                </div>
              ) : prompts.length === 0 && !isLoadingPrompts ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  Click &quot;Refresh&quot; to load prompt templates
                </p>
              ) : (
                <div className="space-y-2">
                  {prompts.map((p) => (
                    <div
                      key={p.id}
                      className="flex items-center justify-between rounded-md border border-border/50 p-3 hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <FileText className="size-4 text-muted-foreground shrink-0" />
                        <div className="min-w-0">
                          <p className="text-sm font-medium">{p.name}</p>
                          {p.description && (
                            <p className="text-xs text-muted-foreground truncate">{p.description}</p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {p.updated_at && (
                          <span className="text-xs text-muted-foreground">
                            {new Date(p.updated_at).toLocaleDateString()}
                          </span>
                        )}
                        <span className={`text-xs px-1.5 py-0.5 rounded ${p.is_active ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"}`}>
                          {p.is_active ? "Active" : "Inactive"}
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditingPrompt({
                            name: p.name,
                            content: p.content,
                            description: p.description || "",
                          })}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => resetPrompt(p.name)}
                          title="Reset to default"
                        >
                          <RotateCcw className="size-3" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => deletePrompt(p.name)}
                          className="text-destructive hover:text-destructive"
                        >
                          <Trash2 className="size-3" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </TabsContent>}
        </Tabs>
      </main>
      <ConfirmDialog />
    </div>
  );
}
