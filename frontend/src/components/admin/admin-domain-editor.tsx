"use client";

import { useState } from "react";
import { Trash2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface AdminDomainEditorProps {
  domains: string[];
  onChange: (domains: string[]) => void;
}

export function AdminDomainEditor({
  domains,
  onChange,
}: AdminDomainEditorProps) {
  const [newDomain, setNewDomain] = useState("");

  const addDomain = () => {
    const domain = newDomain.trim().toLowerCase();
    if (!domain) return;
    if (domains.some((d) => d.toLowerCase() === domain)) return;
    onChange([...domains, domain]);
    setNewDomain("");
  };

  const removeDomain = (index: number) => {
    if (domains.length <= 1) return; // Prevent removing last domain
    onChange(domains.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-muted-foreground">
        Admin Domains
      </h3>
      <p className="text-xs text-muted-foreground">
        Users with email addresses from these domains will have admin access.
      </p>

      {/* Add new domain */}
      <div className="flex items-center gap-2">
        <Input
          placeholder="example.com"
          value={newDomain}
          onChange={(e) => setNewDomain(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addDomain()}
          className="flex-1"
        />
        <Button
          size="sm"
          onClick={addDomain}
          disabled={!newDomain.trim()}
        >
          <Plus className="size-4 mr-1" />
          Add
        </Button>
      </div>

      {/* Existing domains */}
      <div className="space-y-2">
        {domains.map((domain, index) => (
          <div
            key={domain}
            className="flex items-center justify-between rounded-lg border border-border px-4 py-2"
          >
            <span className="text-sm font-medium">@{domain}</span>
            <Button
              variant="ghost"
              size="icon"
              className="size-8 text-muted-foreground hover:text-destructive"
              onClick={() => removeDomain(index)}
              disabled={domains.length <= 1}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
