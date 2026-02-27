"use client";

import { memo, useState, useRef, useCallback } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Target, Trash2, Pencil, Check, Database } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { useAutomationStore } from "@/stores/automation-store";
import type { WorkflowBlock } from "@/types/automation";

type SQLBlockData = WorkflowBlock & { type: "sqlBlock" };

function SQLBlockNodeInner({ data, id }: NodeProps) {
  const blockData = data as unknown as SQLBlockData;
  const toggleActive = useAutomationStore((s) => s.toggleBlockActive);
  const setEndpoint = useAutomationStore((s) => s.setEndpointBlock);
  const removeBlock = useAutomationStore((s) => s.removeBlock);
  const updateBlock = useAutomationStore((s) => s.updateBlock);

  const [isEditing, setIsEditing] = useState(false);
  const [editLabel, setEditLabel] = useState(blockData.label);
  const inputRef = useRef<HTMLInputElement>(null);

  const truncatedSql =
    blockData.sql.length > 200
      ? blockData.sql.slice(0, 200) + "..."
      : blockData.sql;

  const startEdit = useCallback(() => {
    setEditLabel(blockData.label);
    setIsEditing(true);
    setTimeout(() => inputRef.current?.select(), 0);
  }, [blockData.label]);

  const commitEdit = useCallback(() => {
    const trimmed = editLabel.trim();
    if (trimmed && trimmed !== blockData.label) {
      updateBlock(id, { label: trimmed });
    }
    setIsEditing(false);
  }, [editLabel, blockData.label, id, updateBlock]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") commitEdit();
    if (e.key === "Escape") setIsEditing(false);
    // Prevent ReactFlow key bindings from firing while typing
    e.stopPropagation();
  };

  return (
    <div
      className={`w-[280px] rounded-lg border bg-card shadow-md transition-all relative overflow-visible ${
        blockData.isEndpoint
          ? "border-primary shadow-primary/10 shadow-lg ring-2 ring-primary/15"
          : "border-border"
      } ${!blockData.isActive ? "opacity-50" : ""}`}
    >
      {/* Endpoint left-stripe */}
      {blockData.isEndpoint && (
        <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-primary rounded-l-lg" />
      )}

      {/* INPUT handle — top center */}
      <Handle
        type="target"
        position={Position.Top}
        title="Input — drag a connection here"
        style={{
          width: 12,
          height: 12,
          background: "oklch(0.65 0.15 230)",
          border: "2.5px solid oklch(0.25 0.02 230)",
          borderRadius: "50%",
          top: -6,
          cursor: "crosshair",
          transition: "all 0.15s ease",
          boxShadow: "0 0 0 3px oklch(0.65 0.15 230 / 0.15)",
        }}
      />

      {/* Header */}
      <div className="flex items-center gap-1.5 pl-3 pr-2 py-2 border-b border-border bg-muted/20">
        <Database className="size-3 text-muted-foreground flex-shrink-0" />

        {/* Editable label */}
        <div className="flex-1 min-w-0">
          {isEditing ? (
            <input
              ref={inputRef}
              value={editLabel}
              onChange={(e) => setEditLabel(e.target.value)}
              onBlur={commitEdit}
              onKeyDown={handleKeyDown}
              autoFocus
              className="w-full text-xs font-medium bg-transparent border-b border-primary outline-none text-foreground py-px"
            />
          ) : (
            <div className="flex items-center gap-1 group/label">
              <span
                className="text-xs font-medium truncate text-foreground"
                title={blockData.label}
              >
                {blockData.label}
              </span>
              <button
                onClick={startEdit}
                className="opacity-0 group-hover/label:opacity-100 p-0.5 rounded hover:bg-muted transition-opacity"
                title="Rename block"
              >
                <Pencil className="size-2.5 text-muted-foreground" />
              </button>
            </div>
          )}
          {blockData.isEndpoint && (
            <span className="text-[9px] font-semibold text-primary uppercase tracking-wider leading-none">
              Endpoint
            </span>
          )}
        </div>

        {/* Actions */}
        {isEditing ? (
          <button
            onClick={commitEdit}
            className="p-0.5 rounded text-primary hover:bg-muted/60 transition-colors"
            title="Save name"
          >
            <Check className="size-3.5" />
          </button>
        ) : (
          <>
            <Switch
              checked={blockData.isActive}
              onCheckedChange={() => toggleActive(id)}
              className="scale-[0.65] origin-right"
            />
            <button
              onClick={() => setEndpoint(id)}
              className={`p-0.5 rounded transition-colors ${
                blockData.isEndpoint
                  ? "text-primary"
                  : "text-muted-foreground hover:text-primary"
              }`}
              title="Set as endpoint (trigger conditions evaluate here)"
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
          </>
        )}
      </div>

      {/* SQL Preview */}
      <pre className="px-3 py-2 text-[10px] font-mono text-muted-foreground leading-relaxed overflow-hidden max-h-[96px] bg-muted/10">
        {truncatedSql}
      </pre>

      {/* Footer */}
      {(blockData.resultPreview || blockData.sourceMessagePreview) && (
        <div className="px-3 py-1.5 border-t border-border/60 bg-muted/10 flex items-center justify-between">
          {blockData.resultPreview ? (
            <span className="text-[10px] text-muted-foreground">
              {blockData.resultPreview.rowCount} rows &middot;{" "}
              {blockData.resultPreview.columnCount} cols
            </span>
          ) : (
            <span className="text-[10px] text-muted-foreground truncate max-w-[200px]">
              {blockData.sourceMessagePreview}
            </span>
          )}
        </div>
      )}

      {/* OUTPUT handle — bottom center */}
      <Handle
        type="source"
        position={Position.Bottom}
        title="Output — drag to connect to another block"
        style={{
          width: 12,
          height: 12,
          background: "oklch(0.65 0.15 230)",
          border: "2.5px solid oklch(0.25 0.02 230)",
          borderRadius: "50%",
          bottom: -6,
          cursor: "crosshair",
          transition: "all 0.15s ease",
          boxShadow: "0 0 0 3px oklch(0.65 0.15 230 / 0.15)",
        }}
      />
    </div>
  );
}

export const SQLBlockNode = memo(SQLBlockNodeInner);
