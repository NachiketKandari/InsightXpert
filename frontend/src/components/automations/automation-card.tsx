"use client";

import React, { useState } from "react";
import { ChevronRight, Play, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useAutomationStore } from "@/stores/automation-store";
import { cronToHumanReadable } from "@/lib/automation-utils";
import { RunHistory } from "./run-history";
import type { Automation } from "@/types/automation";

interface AutomationCardProps {
  automation: Automation;
  onDelete: (id: string) => void;
}

export function AutomationCard({ automation, onDelete }: AutomationCardProps) {
  const toggleAutomation = useAutomationStore((s) => s.toggleAutomation);
  const runNow = useAutomationStore((s) => s.runNow);
  const [expanded, setExpanded] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isToggling, setIsToggling] = useState(false);

  const handleToggle = async () => {
    setIsToggling(true);
    await toggleAutomation(automation.id);
    setIsToggling(false);
  };

  const handleRunNow = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsRunning(true);
    await runNow(automation.id);
    setIsRunning(false);
  };

  return (
    <div className="rounded-lg border border-border">
      {/* Main row */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <ChevronRight
          className={`size-4 text-muted-foreground shrink-0 transition-transform ${
            expanded ? "rotate-90" : ""
          }`}
        />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium truncate">{automation.name}</p>
            <Badge variant={automation.is_active ? "default" : "secondary"} className="text-xs">
              {automation.is_active ? "Active" : "Paused"}
            </Badge>
          </div>
          {automation.description && (
            <p className="text-xs text-muted-foreground truncate mt-0.5">
              {automation.description}
            </p>
          )}
        </div>

        <div className="flex items-center gap-4 text-xs text-muted-foreground shrink-0">
          <span>{cronToHumanReadable(automation.cron_expression)}</span>
          <span>
            {automation.last_run_at
              ? new Date(automation.last_run_at).toLocaleDateString()
              : "Never run"}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0" onClick={(e) => e.stopPropagation()}>
          <Switch
            checked={automation.is_active}
            onCheckedChange={handleToggle}
            disabled={isToggling}
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={handleRunNow}
            disabled={isRunning}
            className="h-7 px-2"
          >
            <Play className="size-3" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(automation.id);
            }}
            className="h-7 px-2 text-destructive hover:text-destructive"
          >
            <Trash2 className="size-3" />
          </Button>
        </div>
      </div>

      {/* Expanded: run history */}
      {expanded && (
        <div className="border-t border-border bg-muted/10 px-4 py-3">
          <div className="space-y-2">
            <div className="text-xs text-muted-foreground space-y-1">
              <p><span className="font-medium">Query:</span> {automation.nl_query}</p>
              {automation.sql_queries && automation.sql_queries.length > 1 ? (
                <div className="space-y-1">
                  <p className="font-medium">SQL Workflow ({automation.sql_queries.length} steps):</p>
                  {automation.sql_queries.map((sql, i) => (
                    <div key={i} className="rounded border border-border/50">
                      <div className="px-2 py-0.5 bg-muted/30 text-[10px] border-b border-border/50">
                        Step {i + 1}{i === automation.sql_queries.length - 1 ? " (final)" : ""}
                      </div>
                      <pre className="font-mono p-2 overflow-x-auto whitespace-pre-wrap">{sql}</pre>
                    </div>
                  ))}
                </div>
              ) : (
                <pre className="font-mono bg-muted/50 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                  {automation.sql_queries?.[0] ?? automation.sql_query}
                </pre>
              )}
              {automation.next_run_at && (
                <p>
                  <span className="font-medium">Next run:</span>{" "}
                  {new Date(automation.next_run_at).toLocaleString()}
                </p>
              )}
            </div>
            <h4 className="text-xs font-medium pt-2">Run History</h4>
            <RunHistory automationId={automation.id} />
          </div>
        </div>
      )}
    </div>
  );
}
