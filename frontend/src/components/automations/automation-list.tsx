"use client";

import { useEffect } from "react";
import { useAutomationStore } from "@/stores/automation-store";
import { AutomationCard } from "./automation-card";

interface AutomationListProps {
  onDelete: (id: string) => void;
}

export function AutomationList({ onDelete }: AutomationListProps) {
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
      <div className="text-center py-12">
        <p className="text-sm text-muted-foreground">
          No automations yet. Create one from a chat query result.
        </p>
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
