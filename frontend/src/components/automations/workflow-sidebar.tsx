"use client";

import { useState, useCallback, useMemo } from "react";
import { ChevronDown, ChevronRight, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { SchedulePicker } from "./schedule-picker";
import { TriggerConditionBuilder } from "./trigger-condition-builder";
import { AiSqlGenerator } from "./ai-sql-generator";
import { useAutomationStore } from "@/stores/automation-store";
import type { Message } from "@/types/chat";
import type { TriggerCondition, SchedulePreset, WorkflowBlock } from "@/types/automation";

interface WorkflowSidebarProps {
  messages: Message[];
  preset: SchedulePreset;
  customCron: string;
  onScheduleChange: (preset: SchedulePreset, cron: string) => void;
  conditions: TriggerCondition[];
  onConditionsChange: (conditions: TriggerCondition[]) => void;
}

interface CollapsibleProps {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

function Collapsible({ title, defaultOpen = true, children }: CollapsibleProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-border">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full px-4 py-2.5 text-sm font-medium text-foreground hover:bg-muted/50 transition-colors"
      >
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        {title}
      </button>
      {open && <div className="px-4 pb-3">{children}</div>}
    </div>
  );
}

/** Group SQL blocks by source message for the query library display. */
function groupByMessage(messages: Message[]) {
  const groups: Array<{
    messageId: string;
    userQuestion: string;
    sqlEntries: Array<{ sql: string; index: number }>;
  }> = [];

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    if (msg.role !== "assistant") continue;

    let userQuestion = "";
    for (let j = i - 1; j >= 0; j--) {
      if (messages[j].role === "user") {
        userQuestion = messages[j].content;
        break;
      }
    }

    const sqlChunks = msg.chunks.filter((c) => c.type === "sql" && c.sql);
    if (sqlChunks.length === 0) continue;

    groups.push({
      messageId: msg.id,
      userQuestion,
      sqlEntries: sqlChunks.map((c, idx) => ({
        sql: c.sql!,
        index: idx,
      })),
    });
  }
  return groups;
}

export function WorkflowSidebar({
  messages,
  preset,
  customCron,
  onScheduleChange,
  conditions,
  onConditionsChange,
}: WorkflowSidebarProps) {
  const blocks = useAutomationStore((s) => s.workflowBlocks);
  const addBlock = useAutomationStore((s) => s.addBlock);

  const groups = useMemo(() => groupByMessage(messages), [messages]);

  // Track which SQL queries are already on the canvas
  const canvasSqlSet = useMemo(
    () => new Set(blocks.map((b) => b.sql)),
    [blocks],
  );

  const handleAddToCanvas = useCallback(
    (sql: string, label: string, messageId: string) => {
      const maxY = blocks.reduce((max, b) => Math.max(max, b.position.y), -200);
      const newBlock: WorkflowBlock = {
        id: `block-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        sql,
        label: label.slice(0, 60) + (label.length > 60 ? "..." : ""),
        sourceMessageId: messageId,
        sourceMessagePreview: label,
        isActive: true,
        isEndpoint: false,
        resultPreview: null,
        position: { x: 300, y: maxY + 200 },
      };
      addBlock(newBlock);
    },
    [blocks, addBlock],
  );

  // Columns from endpoint block for trigger condition builder
  const endpointBlock = blocks.find((b) => b.isEndpoint);
  const endpointColumns = endpointBlock?.resultPreview
    ? Array.from({ length: endpointBlock.resultPreview.columnCount }, (_, i) => `col_${i}`)
    : [];

  return (
    <div className="h-full w-[280px] border-r border-border overflow-y-auto bg-card flex-shrink-0">
      <Collapsible title="Query Library" defaultOpen>
        <div className="space-y-3">
          {groups.length === 0 && (
            <p className="text-xs text-muted-foreground">No SQL queries found in this conversation.</p>
          )}
          {groups.map((group) => (
            <div key={group.messageId} className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground truncate block">
                {group.userQuestion || "Query"}
              </Label>
              {group.sqlEntries.map((entry) => {
                const alreadyAdded = canvasSqlSet.has(entry.sql);
                return (
                  <div
                    key={`${group.messageId}-${entry.index}`}
                    className={`rounded-md border border-border p-2 ${
                      alreadyAdded ? "opacity-50" : ""
                    }`}
                  >
                    <pre className="text-[10px] font-mono text-muted-foreground overflow-hidden max-h-[60px] leading-relaxed">
                      {entry.sql.slice(0, 150)}
                      {entry.sql.length > 150 ? "..." : ""}
                    </pre>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="w-full mt-1.5 h-7 text-xs"
                      disabled={alreadyAdded}
                      onClick={() =>
                        handleAddToCanvas(
                          entry.sql,
                          group.userQuestion || `SQL Query`,
                          group.messageId,
                        )
                      }
                    >
                      <Plus className="size-3 mr-1" />
                      {alreadyAdded ? "Added" : "Add to Canvas"}
                    </Button>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </Collapsible>

      <Collapsible title="Generate with AI">
        <AiSqlGenerator />
      </Collapsible>

      <Collapsible title="Settings" defaultOpen={false}>
        <div className="space-y-4">
          <SchedulePicker
            preset={preset}
            customCron={customCron}
            onChange={onScheduleChange}
          />
          <TriggerConditionBuilder
            conditions={conditions}
            onChange={onConditionsChange}
            columns={endpointColumns}
            resultShape="tabular"
          />
        </div>
      </Collapsible>
    </div>
  );
}
