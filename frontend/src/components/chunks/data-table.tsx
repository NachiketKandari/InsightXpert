"use client";

import { cn } from "@/lib/utils";

interface DataTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
  /** Max height for the scrollable area. Set to "none" to disable (caller manages scroll). Defaults to "20rem". */
  maxHeight?: string;
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

export function DataTable({
  columns,
  rows,
  maxHeight = "20rem",
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
  const scrollStyle = maxHeight !== "none" ? { maxHeight } : undefined;

  return (
    <div className={cn("", className)}>
      <div
        className={cn(
          "overflow-x-auto rounded-lg border border-border",
          maxHeight !== "none" && "overflow-y-auto",
          tableClassName,
        )}
        style={scrollStyle}
      >
        <table className="w-full text-sm">
          <thead>
            <tr className={cn("bg-muted sticky top-0 z-10", headerRowClassName)}>
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
                    "px-3 py-2 text-left text-xs font-medium text-muted-foreground whitespace-nowrap bg-inherit",
                    headerCellClassName
                  )}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className={loading ? "opacity-40 transition-opacity" : "transition-opacity"}>
            {rows.map((row, i) => (
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
      {maxHeight !== "none" && rows.length > 0 && (
        <p className="text-[10px] text-muted-foreground/60 mt-1 text-right">
          {rows.length} row{rows.length !== 1 ? "s" : ""}
        </p>
      )}
    </div>
  );
}
