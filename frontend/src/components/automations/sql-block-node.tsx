"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Target, Trash2 } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { useAutomationStore } from "@/stores/automation-store";
import type { WorkflowBlock } from "@/types/automation";

type SQLBlockData = WorkflowBlock & { type: "sqlBlock" };

function SQLBlockNodeInner({ data, id }: NodeProps) {
  const blockData = data as unknown as SQLBlockData;
  const toggleActive = useAutomationStore((s) => s.toggleBlockActive);
  const setEndpoint = useAutomationStore((s) => s.setEndpointBlock);
  const removeBlock = useAutomationStore((s) => s.removeBlock);

  const truncatedSql =
    blockData.sql.length > 200
      ? blockData.sql.slice(0, 200) + "..."
      : blockData.sql;

  return (
    <div
      className={`w-[280px] rounded-lg border bg-card shadow-sm transition-all ${
        blockData.isEndpoint
          ? "border-primary ring-2 ring-primary/20"
          : "border-border"
      } ${!blockData.isActive ? "opacity-50" : ""}`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-3 !h-3 !bg-muted-foreground/40 !border-2 !border-background"
      />

      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <span className="flex-1 text-xs font-medium truncate" title={blockData.label}>
          {blockData.label}
        </span>
        <Switch
          checked={blockData.isActive}
          onCheckedChange={() => toggleActive(id)}
          className="scale-75"
        />
        <button
          onClick={() => setEndpoint(id)}
          className={`p-0.5 rounded transition-colors ${
            blockData.isEndpoint
              ? "text-primary"
              : "text-muted-foreground hover:text-primary"
          }`}
          title="Set as endpoint (triggers evaluate here)"
        >
          <Target className="size-3.5" />
        </button>
        <button
          onClick={() => removeBlock(id)}
          className="p-0.5 rounded text-muted-foreground hover:text-destructive transition-colors"
          title="Remove block"
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>

      {/* SQL Preview */}
      <pre className="px-3 py-2 text-[10px] font-mono text-muted-foreground leading-relaxed overflow-hidden max-h-[100px]">
        {truncatedSql}
      </pre>

      {/* Footer */}
      {(blockData.resultPreview || blockData.sourceMessagePreview) && (
        <div className="px-3 py-1.5 border-t border-border flex items-center justify-between">
          {blockData.resultPreview && (
            <span className="text-[10px] text-muted-foreground">
              {blockData.resultPreview.rowCount} rows &middot;{" "}
              {blockData.resultPreview.columnCount} cols
            </span>
          )}
          {blockData.sourceMessagePreview && !blockData.resultPreview && (
            <span className="text-[10px] text-muted-foreground truncate">
              From chat
            </span>
          )}
        </div>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-3 !h-3 !bg-muted-foreground/40 !border-2 !border-background"
      />
    </div>
  );
}

export const SQLBlockNode = memo(SQLBlockNodeInner);
