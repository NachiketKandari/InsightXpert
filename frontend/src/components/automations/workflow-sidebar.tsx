"use client";

import { useState, useCallback, useMemo } from "react";
import {
  ChevronDown,
  ChevronRight,
  Plus,
  Database,
  Sparkles,
  Calendar,
  Library,
} from "lucide-react";
import { SchedulePicker } from "./schedule-picker";
import { TriggerConditionBuilder } from "./trigger-condition-builder";
import { AiSqlGenerator } from "./ai-sql-generator";
import { useAutomationStore } from "@/stores/automation-store";
import type { Message } from "@/types/chat";
import { extractTablesFromSQL } from "@/lib/sql-utils";
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
  icon: React.ReactNode;
  defaultOpen?: boolean;
  badge?: string | number;
  children: React.ReactNode;
}

function Collapsible({ title, icon, defaultOpen = true, badge, children }: CollapsibleProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-border/60">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground/70 hover:text-muted-foreground hover:bg-muted/30 transition-colors"
      >
        <span className="size-4 flex items-center justify-center text-muted-foreground/50">
          {icon}
        </span>
        <span className="flex-1 text-left">{title}</span>
        {badge != null && (
          <span className="text-[9px] font-medium bg-primary/10 text-primary px-1.5 py-0.5 rounded-full">
            {badge}
          </span>
        )}
        {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
      </button>
      {open && <div className="px-3 pb-3">{children}</div>}
    </div>
  );
}

/** Group SQL blocks by source message for the query library display. */
function groupByMessage(messages: Message[]) {
  const groups: Array<{
    messageId: string;
    userQuestion: string;
    sqlEntries: Array<{ sql: string; index: number }>;
    tables: string[];
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

    // Collect all tables referenced across this message's SQL
    const allTables = new Set<string>();
    for (const c of sqlChunks) {
      for (const t of extractTablesFromSQL(c.sql!)) {
        allTables.add(t);
      }
    }

    groups.push({
      messageId: msg.id,
      userQuestion,
      sqlEntries: sqlChunks.map((c, idx) => ({
        sql: c.sql!,
        index: idx,
      })),
      tables: Array.from(allTables),
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
        label: `SQL Query ${blocks.length + 1}`,
        sourceMessageId: messageId,
        sourceMessagePreview: label,
        isActive: true,
        isEndpoint: false,
        resultPreview: null,
        tables: extractTablesFromSQL(sql),
        position: { x: 300, y: maxY + 200 },
      };
      addBlock(newBlock);
    },
    [blocks, addBlock],
  );

  // Columns from endpoint block for trigger condition builder
  const endpointBlock = blocks.find((b) => b.isEndpoint);
  const endpointColumns = endpointBlock?.resultPreview?.columnNames ?? [];

  const totalQueries = groups.reduce((sum, g) => sum + g.sqlEntries.length, 0);

  return (
    <div className="h-full w-[280px] border-r border-border overflow-y-auto bg-card/50 flex-shrink-0 flex flex-col">
      {/* Query Library */}
      <Collapsible
        title="Query Library"
        icon={<Library className="size-3.5" />}
        badge={totalQueries > 0 ? totalQueries : undefined}
        defaultOpen
      >
        <div className="space-y-2.5">
          {groups.length === 0 && (
            <div className="text-center py-4">
              <Database className="size-5 text-muted-foreground/30 mx-auto mb-1.5" />
              <p className="text-[11px] text-muted-foreground/60">
                No SQL queries found in this conversation.
              </p>
            </div>
          )}
          {groups.map((group) => (
            <div key={group.messageId} className="space-y-1.5">
              {/* User question label */}
              <p className="text-[11px] text-muted-foreground font-medium truncate leading-tight">
                {group.userQuestion || "Query"}
              </p>

              {/* Table tags */}
              {group.tables.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {group.tables.map((table) => (
                    <span
                      key={table}
                      className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono bg-primary/8 text-primary/70 border border-primary/15"
                    >
                      {table}
                    </span>
                  ))}
                </div>
              )}

              {/* SQL entries */}
              {group.sqlEntries.map((entry) => {
                const alreadyAdded = canvasSqlSet.has(entry.sql);
                return (
                  <button
                    key={`${group.messageId}-${entry.index}`}
                    className={`w-full text-left rounded-md border overflow-hidden transition-all ${
                      alreadyAdded
                        ? "border-primary/20 bg-primary/[0.03] opacity-50 cursor-default"
                        : "border-border/60 bg-muted/10 hover:border-primary/40 hover:bg-muted/30 cursor-pointer"
                    }`}
                    disabled={alreadyAdded}
                    onClick={() =>
                      !alreadyAdded &&
                      handleAddToCanvas(
                        entry.sql,
                        group.userQuestion || `SQL Query`,
                        group.messageId,
                      )
                    }
                  >
                    <pre className="px-2.5 py-2 text-[10px] font-mono text-muted-foreground overflow-hidden max-h-[48px] leading-relaxed">
                      {entry.sql.slice(0, 120)}
                      {entry.sql.length > 120 ? "..." : ""}
                    </pre>
                    <div className="border-t border-border/40 px-2.5 py-1 flex items-center gap-1.5">
                      {alreadyAdded ? (
                        <>
                          <span className="text-[10px] text-primary">&#10003;</span>
                          <span className="text-[10px] text-muted-foreground/60">On canvas</span>
                        </>
                      ) : (
                        <>
                          <Plus className="size-2.5 text-muted-foreground/50" />
                          <span className="text-[10px] text-muted-foreground/60">Add to canvas</span>
                        </>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </Collapsible>

      {/* Generate with AI */}
      <Collapsible
        title="AI Generator"
        icon={<Sparkles className="size-3.5" />}
        defaultOpen={false}
      >
        <AiSqlGenerator />
      </Collapsible>

      {/* Schedule & Triggers */}
      <Collapsible
        title="Schedule"
        icon={<Calendar className="size-3.5" />}
        defaultOpen
      >
        <div className="space-y-4">
          <SchedulePicker
            preset={preset}
            customCron={customCron}
            onChange={onScheduleChange}
          />
          <div className="border-t border-border/40 pt-3">
            <TriggerConditionBuilder
              conditions={conditions}
              onChange={onConditionsChange}
              columns={endpointColumns}
              resultShape="tabular"
            />
          </div>
        </div>
      </Collapsible>
    </div>
  );
}
