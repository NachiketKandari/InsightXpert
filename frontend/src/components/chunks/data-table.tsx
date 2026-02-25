"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";

interface DataTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
  maxRows?: number;
  showExpandToggle?: boolean;
  showRowNumbers?: boolean;
  rowNumberOffset?: number;
  loading?: boolean;
  className?: string;
  tableClassName?: string;
  headerRowClassName?: string;
  headerCellClassName?: string;
  rowClassName?: (index: number) => string;
  cellClassName?: string;
}

const EXPANDED_CAP = 100;

export function DataTable({
  columns,
  rows,
  maxRows = 10,
  showExpandToggle = true,
  showRowNumbers = false,
  rowNumberOffset = 0,
  loading = false,
  className,
  tableClassName,
  headerRowClassName,
  headerCellClassName,
  rowClassName,
  cellClassName,
}: DataTableProps) {
  const [expanded, setExpanded] = useState(false);
  const canExpand = showExpandToggle && rows.length > maxRows;
  const displayRows = showExpandToggle
    ? expanded
      ? rows.slice(0, EXPANDED_CAP)
      : rows.slice(0, maxRows)
    : rows;
  const cappedTotal = Math.min(rows.length, EXPANDED_CAP);

  return (
    <div className={cn("space-y-2", className)}>
      <div className={cn("overflow-x-auto rounded-lg border border-border", tableClassName)}>
        <table className="w-full text-sm">
          <thead>
            <tr className={cn("bg-muted/50 sticky top-0", headerRowClassName)}>
              {showRowNumbers && (
                <th
                  className={cn(
                    "px-3 py-2 text-left text-xs font-medium text-muted-foreground whitespace-nowrap w-12 bg-inherit",
                    headerCellClassName
                  )}
                >
                  #
                </th>
              )}
              {columns.map((col) => (
                <th
                  key={col}
                  className={cn(
                    "px-3 py-2 text-left text-xs font-medium text-muted-foreground whitespace-nowrap",
                    headerCellClassName
                  )}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className={loading ? "opacity-40 transition-opacity" : "transition-opacity"}>
            {displayRows.map((row, i) => (
              <tr
                key={i}
                className={
                  rowClassName
                    ? rowClassName(i)
                    : i % 2 === 0
                      ? "bg-transparent"
                      : "bg-muted/20"
                }
              >
                {showRowNumbers && (
                  <td className="px-3 py-1.5 text-[11px] text-muted-foreground/60 border-b border-border/20 tabular-nums font-mono">
                    {rowNumberOffset + i + 1}
                  </td>
                )}
                {columns.map((col) => (
                  <td
                    key={col}
                    className={cn(
                      "px-3 py-1.5 font-mono text-xs whitespace-nowrap",
                      cellClassName
                    )}
                  >
                    {row[col] == null ? (
                      <span className="text-muted-foreground italic">null</span>
                    ) : (
                      String(row[col])
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canExpand && (
        <button
          onClick={() => setExpanded((prev) => !prev)}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          {expanded ? (
            <>
              <ChevronUp className="size-3" />
              Show less
            </>
          ) : (
            <>
              <ChevronDown className="size-3" />
              Show all {cappedTotal} rows
            </>
          )}
        </button>
      )}
    </div>
  );
}
