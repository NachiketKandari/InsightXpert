"use client";

import { useEffect, useRef, useState } from "react";
import { Trash2, Plus, ChevronsUpDown } from "lucide-react";
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
  users?: { id: string; email: string; is_active: boolean }[];
  onChange: (mappings: UserOrgMapping[]) => void;
}

export function UserOrgMappingsEditor({
  mappings,
  organizations,
  users = [],
  onChange,
}: UserOrgMappingsEditorProps) {
  const [newEmail, setNewEmail] = useState("");
  const [newOrgId, setNewOrgId] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const orgList = Object.values(organizations);
  const mappedEmails = new Set(mappings.map((m) => m.email.toLowerCase()));

  // Users not yet assigned to any org mapping, filtered by current input
  const suggestions = users.filter((u) => {
    if (mappedEmails.has(u.email.toLowerCase())) return false;
    if (!newEmail.trim()) return true;
    return u.email.toLowerCase().includes(newEmail.trim().toLowerCase());
  });

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const selectSuggestion = (email: string) => {
    setNewEmail(email);
    setDropdownOpen(false);
  };

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

  const showDropdown = dropdownOpen && users.length > 0 && suggestions.length > 0;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-muted-foreground">
        User-Organization Mappings
      </h3>

      {/* Add new mapping */}
      <div className="flex items-end gap-2">
        {/* Email input with autocomplete */}
        <div ref={containerRef} className="relative flex-1">
          <div className="relative">
            <Input
              placeholder={users.length > 0 ? "Search or type email…" : "user@example.com"}
              value={newEmail}
              onChange={(e) => {
                setNewEmail(e.target.value);
                setDropdownOpen(true);
              }}
              onFocus={() => setDropdownOpen(true)}
              onKeyDown={(e) => {
                if (e.key === "Enter") { addMapping(); setDropdownOpen(false); }
                if (e.key === "Escape") setDropdownOpen(false);
              }}
              className="pr-8"
            />
            {users.length > 0 && (
              <ChevronsUpDown
                className="absolute right-2 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground cursor-pointer"
                onClick={() => setDropdownOpen((v) => !v)}
              />
            )}
          </div>

          {showDropdown && (
            <div className="absolute z-50 mt-1 w-full rounded-md border border-border bg-popover shadow-md overflow-hidden">
              <div className="max-h-48 overflow-y-auto py-1">
                {suggestions.map((u) => (
                  <button
                    key={u.id}
                    type="button"
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent text-left"
                    onMouseDown={(e) => {
                      e.preventDefault(); // prevent input blur before click fires
                      selectSuggestion(u.email);
                    }}
                  >
                    <span className="flex-1 truncate">{u.email}</span>
                    {!u.is_active && (
                      <span className="text-xs text-muted-foreground shrink-0">inactive</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}
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
