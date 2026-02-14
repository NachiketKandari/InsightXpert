"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

interface DataTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
  maxRows?: number;
}

const EXPANDED_CAP = 100;

export function DataTable({ columns, rows, maxRows = 10 }: DataTableProps) {
  const [expanded, setExpanded] = useState(false);
  const canExpand = rows.length > maxRows;
  const displayRows = expanded
    ? rows.slice(0, EXPANDED_CAP)
    : rows.slice(0, maxRows);
  const cappedTotal = Math.min(rows.length, EXPANDED_CAP);

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-muted/50 sticky top-0">
              {columns.map((col) => (
                <th
                  key={col}
                  className="px-3 py-2 text-left text-xs font-medium text-muted-foreground whitespace-nowrap"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayRows.map((row, i) => (
              <tr
                key={i}
                className={i % 2 === 0 ? "bg-transparent" : "bg-muted/20"}
              >
                {columns.map((col) => (
                  <td
                    key={col}
                    className="px-3 py-1.5 font-mono text-xs whitespace-nowrap"
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
