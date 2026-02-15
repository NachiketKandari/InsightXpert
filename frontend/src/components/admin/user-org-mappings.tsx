"use client";

import { useState } from "react";
import { Trash2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { UserOrgMapping, OrgConfig } from "@/types/admin";

interface UserOrgMappingsEditorProps {
  mappings: UserOrgMapping[];
  organizations: Record<string, OrgConfig>;
  onChange: (mappings: UserOrgMapping[]) => void;
}

export function UserOrgMappingsEditor({
  mappings,
  organizations,
  onChange,
}: UserOrgMappingsEditorProps) {
  const [newEmail, setNewEmail] = useState("");
  const [newOrgId, setNewOrgId] = useState("");

  const orgList = Object.values(organizations);

  const addMapping = () => {
    const email = newEmail.trim().toLowerCase();
    if (!email || !newOrgId) return;
    if (mappings.some((m) => m.email.toLowerCase() === email)) return;
    onChange([...mappings, { email, org_id: newOrgId }]);
    setNewEmail("");
    setNewOrgId("");
  };

  const removeMapping = (index: number) => {
    onChange(mappings.filter((_, i) => i !== index));
  };

  const getOrgName = (orgId: string) =>
    organizations[orgId]?.org_name ?? orgId;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-muted-foreground">
        User-Organization Mappings
      </h3>

      {/* Add new mapping */}
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <Input
            placeholder="user@example.com"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addMapping()}
          />
        </div>
        <Select value={newOrgId} onValueChange={setNewOrgId}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Select org" />
          </SelectTrigger>
          <SelectContent>
            {orgList.map((org) => (
              <SelectItem key={org.org_id} value={org.org_id}>
                {org.org_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          size="sm"
          onClick={addMapping}
          disabled={!newEmail.trim() || !newOrgId}
        >
          <Plus className="size-4 mr-1" />
          Add
        </Button>
      </div>

      {/* Existing mappings */}
      {mappings.length === 0 ? (
        <p className="text-sm text-muted-foreground">No mappings configured.</p>
      ) : (
        <div className="space-y-2">
          {mappings.map((mapping, index) => (
            <div
              key={mapping.email}
              className="flex items-center justify-between rounded-lg border border-border px-4 py-2"
            >
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium">{mapping.email}</span>
                <span className="text-xs text-muted-foreground">
                  {getOrgName(mapping.org_id)}
                </span>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="size-8 text-muted-foreground hover:text-destructive"
                onClick={() => removeMapping(index)}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
