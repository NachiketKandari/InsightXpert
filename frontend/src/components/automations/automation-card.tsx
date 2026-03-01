"use client";

import React, { useState, useCallback } from "react";
import {
  ChevronRight,
  Play,
  Trash2,
  RotateCw,
  Square,
  Zap,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Timer,
  Pencil,
} from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { useAutomationStore } from "@/stores/automation-store";
import { cronToHumanReadable } from "@/lib/automation-utils";
import { RunHistory } from "./run-history";
import type { Automation, AutomationRun } from "@/types/automation";

interface AutomationCardProps {
  automation: Automation;
  onDelete: (id: string) => void;
}

function RunResultToast({ run }: { run: AutomationRun }) {
  const firedCount = run.triggers_fired?.filter((t) => t.fired).length ?? 0;
  const totalCount = run.triggers_fired?.length ?? 0;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        {run.status === "success" ? (
          <CheckCircle2 className="size-4 text-emerald-500" />
        ) : run.status === "error" ? (
          <XCircle className="size-4 text-red-500" />
        ) : (
          <AlertTriangle className="size-4 text-amber-500" />
        )}
        <span className="text-sm font-medium capitalize">{run.status.replace("_", " ")}</span>
      </div>
      {run.row_count != null && (
        <p className="text-xs text-muted-foreground">
          {run.row_count} row{run.row_count !== 1 ? "s" : ""} returned
          {run.execution_time_ms != null && ` in ${run.execution_time_ms}ms`}
        </p>
      )}
      {totalCount > 0 && (
        <p className="text-xs text-muted-foreground">
          Triggers: {firedCount}/{totalCount} fired
        </p>
      )}
      {run.error_message && (
        <p className="text-xs text-red-400 truncate max-w-[280px]">{run.error_message}</p>
      )}
    </div>
  );
}

export function AutomationCard({ automation, onDelete }: AutomationCardProps) {
  const toggleAutomation = useAutomationStore((s) => s.toggleAutomation);
  const runNow = useAutomationStore((s) => s.runNow);
  const startTestTrigger = useAutomationStore((s) => s.startTestTrigger);
  const stopTestTrigger = useAutomationStore((s) => s.stopTestTrigger);
  const openWorkflowBuilderForEdit = useAutomationStore((s) => s.openWorkflowBuilderForEdit);
  const testState = useAutomationStore((s) => s.activeTestTriggers[automation.id]);

  const [expanded, setExpanded] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isToggling, setIsToggling] = useState(false);
  const [testInterval, setTestInterval] = useState(30);
  const [showTestConfig, setShowTestConfig] = useState(false);

  const handleToggle = async () => {
    setIsToggling(true);
    await toggleAutomation(automation.id);
    setIsToggling(false);
  };

  const handleTriggerNow = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsRunning(true);
    const result = await runNow(automation.id);
    setIsRunning(false);

    if (result?.run) {
      toast(<RunResultToast run={result.run} />, {
        duration: 5000,
      });
    } else if (result) {
      toast.info(result.message);
    } else {
      toast.error("Failed to trigger automation");
    }
  }, [runNow, automation.id]);

  const handleStartTest = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    startTestTrigger(automation.id, testInterval);
    setShowTestConfig(false);
    toast.info(`Test mode started — running every ${testInterval}s`, { duration: 3000 });
  }, [startTestTrigger, automation.id, testInterval]);

  const handleStopTest = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    stopTestTrigger(automation.id);
    toast.info("Test mode stopped", { duration: 2000 });
  }, [stopTestTrigger, automation.id]);

  const isTestActive = !!testState;

  return (
    <div className={`rounded-lg border transition-colors ${
      isTestActive
        ? "border-amber-500/40 bg-amber-500/[0.02]"
        : "border-border"
    }`}>
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
            <Badge variant={automation.is_active ? "default" : "secondary"} className="text-[10px] px-1.5 py-0">
              {automation.is_active ? "Active" : "Paused"}
            </Badge>
            {isTestActive && (
              <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-amber-500/50 text-amber-500 animate-pulse">
                Testing
              </Badge>
            )}
          </div>
          {automation.description && (
            <p className="text-xs text-muted-foreground truncate mt-0.5">
              {automation.description}
            </p>
          )}
        </div>

        <div className="flex items-center gap-3 text-[11px] text-muted-foreground shrink-0">
          <span className="flex items-center gap-1">
            <Clock className="size-3" />
            {cronToHumanReadable(automation.cron_expression)}
          </span>
          <span>
            {automation.last_run_at
              ? new Date(automation.last_run_at).toLocaleDateString()
              : "Never run"}
          </span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
          <Switch
            checked={automation.is_active}
            onCheckedChange={handleToggle}
            disabled={isToggling}
            className="scale-90"
          />

          {/* Trigger Now */}
          <Button
            variant="ghost"
            size="sm"
            onClick={handleTriggerNow}
            disabled={isRunning}
            className="h-7 px-2 gap-1 text-xs"
            title="Trigger now"
          >
            {isRunning ? (
              <RotateCw className="size-3 animate-spin" />
            ) : (
              <Zap className="size-3" />
            )}
          </Button>

          {/* Test Trigger toggle */}
          {isTestActive ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleStopTest}
              className="h-7 px-2 gap-1 text-xs text-amber-500 hover:text-amber-400 hover:bg-amber-500/10"
              title="Stop test trigger"
            >
              <Square className="size-3 fill-current" />
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                setShowTestConfig(!showTestConfig);
              }}
              className="h-7 px-2 gap-1 text-xs"
              title="Start test trigger"
            >
              <Timer className="size-3" />
            </Button>
          )}

          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              openWorkflowBuilderForEdit(automation);
            }}
            className="h-7 px-2 gap-1 text-xs"
            title="Edit automation"
          >
            <Pencil className="size-3" />
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

      {/* Test config bar */}
      {showTestConfig && !isTestActive && (
        <div className="px-4 py-2.5 border-t border-border bg-muted/20 flex items-center gap-3">
          <Timer className="size-3.5 text-muted-foreground shrink-0" />
          <span className="text-xs text-muted-foreground shrink-0">Run every</span>
          <Input
            type="number"
            min={5}
            max={3600}
            value={testInterval}
            onChange={(e) => setTestInterval(Math.max(5, Number(e.target.value) || 30))}
            className="h-7 w-20 text-xs"
            onClick={(e) => e.stopPropagation()}
          />
          <span className="text-xs text-muted-foreground shrink-0">seconds</span>
          <Button
            size="sm"
            onClick={handleStartTest}
            className="h-7 text-xs gap-1"
          >
            <Play className="size-3" />
            Start Test
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              setShowTestConfig(false);
            }}
            className="h-7 text-xs"
          >
            Cancel
          </Button>
        </div>
      )}

      {/* Live test status bar */}
      {isTestActive && (
        <div className="px-4 py-2 border-t border-amber-500/20 bg-amber-500/[0.03] flex items-center gap-3">
          <div className="size-2 rounded-full bg-amber-500 animate-pulse shrink-0" />
          <span className="text-xs font-medium text-amber-500">
            Test Mode
          </span>
          <span className="text-xs text-muted-foreground">
            Every {testState.intervalSeconds}s
            {testState.iterationCount > 0 && ` \u00b7 ${testState.iterationCount} run${testState.iterationCount !== 1 ? "s" : ""}`}
          </span>
          {testState.isRunning && (
            <RotateCw className="size-3 text-amber-500 animate-spin" />
          )}
          {testState.lastResult?.run && (
            <Badge
              variant={testState.lastResult.run.status === "success" ? "default" : testState.lastResult.run.status === "error" ? "destructive" : "secondary"}
              className="text-[10px] px-1.5 py-0 ml-auto"
            >
              Last: {testState.lastResult.run.status}
              {testState.lastResult.run.triggers_fired && (
                <> — {testState.lastResult.run.triggers_fired.filter(t => t.fired).length}/{testState.lastResult.run.triggers_fired.length} fired</>
              )}
            </Badge>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={handleStopTest}
            className="h-6 px-2 text-[11px] text-amber-500 hover:text-amber-400 hover:bg-amber-500/10 ml-auto shrink-0"
          >
            <Square className="size-2.5 mr-1 fill-current" />
            Stop
          </Button>
        </div>
      )}

      {/* Expanded: details + run history */}
      {expanded && (
        <div className="border-t border-border bg-muted/[0.03] px-4 py-3">
          <div className="space-y-3">
            <div className="text-xs text-muted-foreground space-y-2">
              <p>
                <span className="font-medium text-foreground/70">Query:</span>{" "}
                {automation.nl_query}
              </p>
              {automation.sql_queries && automation.sql_queries.length > 1 ? (
                <div className="space-y-1.5">
                  <p className="font-medium text-foreground/70">
                    SQL Workflow ({automation.sql_queries.length} steps)
                  </p>
                  {automation.sql_queries.map((sql, i) => (
                    <div key={i} className="rounded border border-border/60 overflow-hidden">
                      <div className="px-2.5 py-1 bg-muted/40 text-[10px] font-medium text-muted-foreground border-b border-border/60">
                        Step {i + 1}
                        {i === automation.sql_queries.length - 1 && (
                          <span className="ml-1.5 text-primary">(final)</span>
                        )}
                      </div>
                      <pre className="font-mono text-[11px] p-2.5 overflow-x-auto whitespace-pre-wrap leading-relaxed text-muted-foreground">
                        {sql}
                      </pre>
                    </div>
                  ))}
                </div>
              ) : (
                <pre className="font-mono text-[11px] bg-muted/30 rounded border border-border/60 p-2.5 overflow-x-auto whitespace-pre-wrap leading-relaxed">
                  {automation.sql_queries?.[0] ?? automation.sql_query}
                </pre>
              )}
              {automation.next_run_at && (
                <p className="flex items-center gap-1.5">
                  <Clock className="size-3" />
                  <span className="font-medium text-foreground/70">Next run:</span>{" "}
                  {new Date(automation.next_run_at).toLocaleString()}
                </p>
              )}
            </div>
            <div className="pt-1">
              <h4 className="text-xs font-medium mb-2 text-foreground/70">Run History</h4>
              <RunHistory automationId={automation.id} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
