"use client";

import { useEffect } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAutomationStore } from "@/stores/automation-store";
import { AutomationCard } from "./automation-card";

interface AutomationListProps {
  onDelete: (id: string) => void;
  onNew?: () => void;
}

export function AutomationList({ onDelete, onNew }: AutomationListProps) {
  const automations = useAutomationStore((s) => s.automations);
  const isLoading = useAutomationStore((s) => s.isLoading);
  const fetchAutomations = useAutomationStore((s) => s.fetchAutomations);

  useEffect(() => {
    fetchAutomations();
  }, [fetchAutomations]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (automations.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <p className="text-sm text-muted-foreground">
          No automations yet. Create one to schedule recurring queries and get notified on results.
        </p>
        {onNew && (
          <Button size="sm" onClick={onNew}>
            <Plus className="size-4 mr-1.5" />
            New automation
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {automations.map((auto) => (
        <AutomationCard key={auto.id} automation={auto} onDelete={onDelete} />
      ))}
    </div>
  );
}
