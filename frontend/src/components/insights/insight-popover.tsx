"use client";

import { Button } from "@/components/ui/button";
import { useInsightStore } from "@/stores/insight-store";
import { CATEGORY_COLOR, DEFAULT_CATEGORY_COLOR } from "./constants";

interface InsightPopoverProps {
  onShowAll: () => void;
}

export function InsightPopover({ onShowAll }: InsightPopoverProps) {
  const insights = useInsightStore((s) => s.insights);

  const recent = insights.slice(0, 5);

  return (
    <div className="w-80 max-h-96 overflow-y-auto rounded-lg border border-border bg-background shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-sm font-medium">Insights</span>
      </div>

      {/* List */}
      {recent.length === 0 ? (
        <div className="py-6 text-center text-sm text-muted-foreground">
          No insights yet
        </div>
      ) : (
        <div className="divide-y divide-border/50">
          {recent.map((i) => (
            <div
              key={i.id}
              className="px-3 py-2.5 hover:bg-muted/50 transition-colors"
            >
              <p className="text-sm font-medium truncate">{i.title}</p>
              <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                {i.categories.slice(0, 3).map((cat) => (
                  <span
                    key={cat}
                    className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium ${CATEGORY_COLOR[cat] ?? DEFAULT_CATEGORY_COLOR}`}
                  >
                    {cat.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                {new Date(i.created_at).toLocaleString()}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Footer */}
      <div className="border-t border-border px-3 py-1.5 text-center">
        <Button
          variant="ghost"
          size="sm"
          className="w-full h-7 text-xs text-amber-600 hover:text-amber-600 hover:bg-amber-500/10 dark:text-amber-400 dark:hover:text-amber-400"
          onClick={onShowAll}
        >
          See all insights
        </Button>
      </div>
    </div>
  );
}
