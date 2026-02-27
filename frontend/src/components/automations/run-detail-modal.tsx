"use client";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { OPERATOR_LABELS } from "@/lib/automation-utils";
import type { AutomationRun } from "@/types/automation";

interface RunDetailModalProps {
  run: AutomationRun | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive"> = {
  success: "default",
  no_trigger: "secondary",
  error: "destructive",
};

export function RunDetailModal({ run, open, onOpenChange }: RunDetailModalProps) {
  if (!run) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Run Details</DialogTitle>
          <DialogDescription>
            {new Date(run.created_at).toLocaleString()}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Status & Timing */}
          <div className="flex items-center gap-3">
            <Badge variant={STATUS_VARIANT[run.status] ?? "secondary"}>
              {run.status}
            </Badge>
            {run.execution_time_ms != null && (
              <span className="text-sm text-muted-foreground">
                {run.execution_time_ms}ms
              </span>
            )}
            {run.row_count != null && (
              <span className="text-sm text-muted-foreground">
                {run.row_count} row{run.row_count !== 1 ? "s" : ""}
              </span>
            )}
          </div>

          {/* Error */}
          {run.error_message && (
            <div className="rounded-md bg-destructive/10 border border-destructive/20 p-3">
              <p className="text-sm text-destructive">{run.error_message}</p>
            </div>
          )}

          {/* Triggers */}
          {run.triggers_fired && run.triggers_fired.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium">Trigger Results</h4>
              <div className="space-y-1">
                {run.triggers_fired.map((tr, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 text-sm rounded-md border border-border p-2"
                  >
                    <Badge variant={tr.fired ? "default" : "secondary"} className="text-xs">
                      {tr.fired ? "Fired" : "Not fired"}
                    </Badge>
                    <span className="text-muted-foreground">
                      {tr.condition.type}
                      {tr.condition.column && ` (${tr.condition.column})`}
                      {tr.condition.operator && ` ${OPERATOR_LABELS[tr.condition.operator] ?? tr.condition.operator}`}
                      {tr.condition.value != null && ` ${tr.condition.value}`}
                    </span>
                    {tr.actual_value != null && (
                      <span className="text-xs text-muted-foreground ml-auto">
                        actual: {tr.actual_value}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Result Data */}
          {run.result_json && run.result_json.columns.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium">Result Data</h4>
              <div className="overflow-x-auto rounded-md border border-border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted/50">
                      {run.result_json.columns.map((col) => (
                        <th key={col} className="px-3 py-2 text-left font-medium text-xs">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {run.result_json.rows.slice(0, 50).map((row, i) => (
                      <tr key={i} className="border-b border-border/50 last:border-0">
                        {run.result_json!.columns.map((col) => (
                          <td key={col} className="px-3 py-1.5 text-xs">
                            {String(row[col] ?? "")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {run.result_json.rows.length > 50 && (
                  <p className="text-xs text-muted-foreground p-2 text-center">
                    Showing 50 of {run.result_json.rows.length} rows
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
