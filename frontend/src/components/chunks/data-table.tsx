"use client";

interface DataTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
  maxRows?: number;
}

export function DataTable({ columns, rows, maxRows = 10 }: DataTableProps) {
  const displayRows = rows.slice(0, maxRows);
  const isTruncated = rows.length > maxRows;

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
      {isTruncated && (
        <p className="text-xs text-muted-foreground">
          Showing {maxRows} of {rows.length} rows
        </p>
      )}
    </div>
  );
}
