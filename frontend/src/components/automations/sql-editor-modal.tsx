"use client";

import { useState, useCallback } from "react";
import { Play, Save, X, Loader2, Database } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAutomationStore } from "@/stores/automation-store";
import { apiCall } from "@/lib/api";

interface SqlResult {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  execution_time_ms: number;
}

interface SqlEditorModalProps {
  blockId: string;
  blockLabel: string;
  sql: string;
  isOpen: boolean;
  onClose: () => void;
}

export function SqlEditorModal({
  blockId,
  blockLabel,
  sql,
  isOpen,
  onClose,
}: SqlEditorModalProps) {
  const [editSql, setEditSql] = useState(sql);
  const [result, setResult] = useState<SqlResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const updateBlock = useAutomationStore((s) => s.updateBlock);

  // Reset state when modal opens or sql prop changes (render-time adjustment)
  const [prevKey, setPrevKey] = useState({ isOpen, sql });
  if (isOpen && (isOpen !== prevKey.isOpen || sql !== prevKey.sql)) {
    setEditSql(sql);
    setResult(null);
    setError(null);
  }
  if (isOpen !== prevKey.isOpen || sql !== prevKey.sql) {
    setPrevKey({ isOpen, sql });
  }

  const handleRun = useCallback(async () => {
    if (!editSql.trim()) return;
    setIsRunning(true);
    setError(null);
    setResult(null);
    const data = await apiCall<SqlResult>("/api/sql/execute", {
      method: "POST",
      body: JSON.stringify({ sql: editSql.trim() }),
    });
    setIsRunning(false);
    if (data) {
      setResult(data);
    } else {
      setError("Query failed. Check the SQL syntax and try again.");
    }
  }, [editSql]);

  const handleSave = useCallback(() => {
    const trimmed = editSql.trim();
    if (trimmed && trimmed !== sql) {
      updateBlock(blockId, { sql: trimmed });
    }
    onClose();
  }, [blockId, editSql, sql, updateBlock, onClose]);

  const hasChanges = editSql.trim() !== sql.trim();

  return (
    <Dialog open={isOpen} onOpenChange={(v) => !v && onClose()}>
      <DialogContent showCloseButton={false} className="max-w-3xl w-[90vw] h-[80vh] max-h-[80vh] flex flex-col gap-0 p-0 overflow-hidden">
        <DialogHeader className="px-4 py-3 border-b border-border flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Database className="size-3.5 text-muted-foreground" />
              <DialogTitle className="text-sm font-medium">{blockLabel}</DialogTitle>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
              aria-label="Close"
            >
              <X className="size-4" />
            </button>
          </div>
          <DialogDescription className="sr-only">
            View, edit and run the SQL query for this workflow block
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col flex-1 overflow-hidden p-4 gap-3 min-h-0">
          {/* SQL Editor */}
          <Textarea
            value={editSql}
            onChange={(e) => setEditSql(e.target.value)}
            className="font-mono text-xs resize-none flex-shrink-0 h-[140px] min-h-[80px]"
            placeholder="SELECT ..."
            onKeyDown={(e) => {
              // Ctrl+Enter / Cmd+Enter to run
              if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                e.preventDefault();
                handleRun();
              }
            }}
          />

          {/* Actions */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <Button
              size="sm"
              onClick={handleRun}
              disabled={isRunning || !editSql.trim()}
              title="Run SQL query (Ctrl+Enter)"
            >
              {isRunning ? (
                <Loader2 className="size-3.5 mr-1.5 animate-spin" />
              ) : (
                <Play className="size-3.5 mr-1.5" />
              )}
              {isRunning ? "Running..." : "Run SQL"}
            </Button>
            {hasChanges && (
              <Button
                size="sm"
                variant="outline"
                onClick={handleSave}
                title="Save SQL changes to the block"
              >
                <Save className="size-3.5 mr-1.5" />
                Save Changes
              </Button>
            )}
            {result && (
              <span className="text-xs text-muted-foreground">
                {result.row_count} row{result.row_count !== 1 ? "s" : ""} &middot; {result.execution_time_ms}ms
              </span>
            )}
            <span className="ml-auto text-[10px] text-muted-foreground/50">
              Ctrl+Enter to run
            </span>
          </div>

          {/* Error */}
          {error && (
            <p className="text-xs text-destructive flex-shrink-0 bg-destructive/5 border border-destructive/20 rounded-md px-3 py-2">
              {error}
            </p>
          )}

          {/* Results table */}
          {result && result.columns.length > 0 && (
            <div className="flex-1 overflow-auto border border-border rounded-md min-h-0">
              <table className="w-full text-xs border-collapse">
                <thead className="bg-muted/50 sticky top-0">
                  <tr>
                    {result.columns.map((col) => (
                      <th
                        key={col}
                        className="text-left px-2.5 py-1.5 font-medium border-b border-border text-muted-foreground whitespace-nowrap"
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.slice(0, 200).map((row, i) => (
                    <tr
                      key={i}
                      className={i % 2 === 0 ? "bg-background" : "bg-muted/20"}
                    >
                      {result.columns.map((col) => (
                        <td
                          key={col}
                          className="px-2.5 py-1 border-b border-border/40 font-mono truncate max-w-[240px]"
                          title={String(row[col] ?? "")}
                        >
                          {String(row[col] ?? "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.row_count > 200 && (
                <p className="text-[10px] text-muted-foreground text-center py-2 border-t border-border">
                  Showing first 200 of {result.row_count} rows
                </p>
              )}
            </div>
          )}

          {result && result.columns.length === 0 && (
            <p className="text-xs text-muted-foreground flex-shrink-0">
              Query returned no rows.
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
