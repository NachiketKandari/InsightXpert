"use client";

import { useEffect, useCallback, useState } from "react";
import { Lightbulb, ExternalLink, Clock, Bookmark, Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useInsightStore } from "@/stores/insight-store";
import { useClientConfig } from "@/hooks/use-client-config";
import { InsightCard } from "./insight-card";
import { CATEGORY_COLOR, DEFAULT_CATEGORY_COLOR } from "./constants";
import type { Insight } from "@/types/insight";

type Filter = "all" | "bookmarked" | "manual";

interface InsightAllModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function InsightAllModal({ open, onOpenChange }: InsightAllModalProps) {
  const { isAdmin, orgId } = useClientConfig();
  const allInsights = useInsightStore((s) => s.allInsights);
  const isLoadingAll = useInsightStore((s) => s.isLoadingAll);
  const fetchAllInsights = useInsightStore((s) => s.fetchAllInsights);
  const bookmarkInsight = useInsightStore((s) => s.bookmarkInsight);
  const deleteInsight = useInsightStore((s) => s.deleteInsight);
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedInsight, setSelectedInsight] = useState<Insight | null>(null);

  useEffect(() => {
    if (open) fetchAllInsights();
  }, [open, fetchAllInsights]);

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) setSelectedInsight(null);
      onOpenChange(nextOpen);
    },
    [onOpenChange],
  );

  const bookmarkedCount = allInsights.filter((i) => i.is_bookmarked).length;
  const manualCount = allInsights.filter((i) => i.source === "manual").length;
  const filtered =
    filter === "bookmarked"
      ? allInsights.filter((i) => i.is_bookmarked)
      : filter === "manual"
        ? allInsights.filter((i) => i.source === "manual")
        : allInsights;

  const handleClick = (insight: Insight) => {
    setSelectedInsight(insight);
  };

  const handleNavigateToConversation = (conversationId: string) => {
    onOpenChange(false);
    window.location.href = `/?c=${conversationId}`;
  };

  const isOrgAdmin = isAdmin && !!orgId;
  const isSuperAdmin = isAdmin && !orgId;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="w-[95vw] max-w-4xl h-[80vh] flex flex-col p-0 bg-card border-border/60 shadow-2xl">
        <DialogHeader className="px-6 pt-5 pb-3 shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <Lightbulb className="size-5 text-amber-500" />
            {isSuperAdmin
              ? "All Insights"
              : isOrgAdmin
                ? "Organization Insights"
                : "Your Insights"}
          </DialogTitle>
          <DialogDescription>
            {isSuperAdmin
              ? "Data insights across all users and organizations"
              : isOrgAdmin
                ? "Data insights for all users in your organization"
                : "Data insights discovered from your conversations"}
          </DialogDescription>
        </DialogHeader>

        {/* Filter bar */}
        <InsightFilterBar
          total={allInsights.length}
          bookmarkedCount={bookmarkedCount}
          manualCount={manualCount}
          filter={filter}
          onFilterChange={setFilter}
          className="border-b border-border px-6 pb-3 shrink-0"
        />

        {/* Split view: list + detail */}
        <div className="flex flex-1 min-h-0 overflow-hidden">
          {/* Insight list */}
          <div
            className={`overflow-y-auto space-y-1 p-3 min-h-0 ${
              selectedInsight ? "w-1/2 border-r border-border" : "w-full"
            }`}
          >
            {isLoadingAll ? (
              <InsightLoading />
            ) : filtered.length === 0 ? (
              <InsightEmptyState filter={filter} />
            ) : (
              filtered.map((i) => (
                <InsightCard
                  key={i.id}
                  insight={i}
                  onClick={handleClick}
                  onBookmark={bookmarkInsight}
                  showUserEmail={isAdmin}
                  isSelected={selectedInsight?.id === i.id}
                />
              ))
            )}
          </div>

          {/* Detail panel */}
          {selectedInsight && (
            <div className="w-1/2 overflow-y-auto p-5">
              <InsightDetail
                insight={selectedInsight}
                onNavigateToConversation={handleNavigateToConversation}
                onBookmark={bookmarkInsight}
                onDelete={(id) => {
                  deleteInsight(id);
                  setSelectedInsight(null);
                }}
              />
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ---------- Filter bar ----------

function InsightFilterBar({
  total,
  bookmarkedCount,
  manualCount,
  filter,
  onFilterChange,
  className,
}: {
  total: number;
  bookmarkedCount: number;
  manualCount: number;
  filter: Filter;
  onFilterChange: (f: Filter) => void;
  className?: string;
}) {
  return (
    <div className={`flex items-center justify-between ${className ?? ""}`}>
      <div className="flex items-center gap-1">
        <Button
          variant={filter === "all" ? "secondary" : "ghost"}
          size="sm"
          className="h-7 text-xs"
          onClick={() => onFilterChange("all")}
        >
          All ({total})
        </Button>
        <Button
          variant={filter === "manual" ? "secondary" : "ghost"}
          size="sm"
          className="h-7 text-xs"
          onClick={() => onFilterChange("manual")}
        >
          <Lightbulb className="size-3 mr-1" />
          Manual ({manualCount})
        </Button>
        <Button
          variant={filter === "bookmarked" ? "secondary" : "ghost"}
          size="sm"
          className="h-7 text-xs"
          onClick={() => onFilterChange("bookmarked")}
        >
          <Bookmark className="size-3 mr-1" />
          Bookmarked ({bookmarkedCount})
        </Button>
      </div>
    </div>
  );
}

// ---------- Detail panel ----------

function InsightDetail({
  insight,
  onNavigateToConversation,
  onBookmark,
  onDelete,
}: {
  insight: Insight;
  onNavigateToConversation: (id: string) => void;
  onBookmark: (id: string, bookmarked: boolean) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="space-y-5">
      {/* Title + actions */}
      <div>
        <h3 className="text-base font-semibold">{insight.title}</h3>
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          <span
            className={`inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[10px] font-medium ${
              insight.source === "manual"
                ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                : "bg-blue-500/15 text-blue-600 dark:text-blue-400"
            }`}
          >
            {insight.source === "manual" ? (
              <><Lightbulb className="size-2.5" /> Manual</>
            ) : (
              "Auto"
            )}
          </span>
          {insight.categories.map((cat) => (
            <span
              key={cat}
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${CATEGORY_COLOR[cat] ?? DEFAULT_CATEGORY_COLOR}`}
            >
              {cat.replace(/_/g, " ")}
            </span>
          ))}
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <Clock className="size-3" />
            {new Date(insight.created_at).toLocaleString()}
          </span>
        </div>
      </div>

      {/* User note (manual insights) */}
      {insight.user_note && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
          <p className="text-xs font-medium text-amber-600 dark:text-amber-400 mb-1">User Note</p>
          <p className="text-sm leading-relaxed italic">{insight.user_note}</p>
        </div>
      )}

      {/* Summary */}
      <div className="rounded-md border border-border/50 bg-muted/30 p-3">
        <p className="text-sm leading-relaxed">{insight.summary}</p>
      </div>

      {/* Full content */}
      <div className="space-y-2">
        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Full Analysis
        </h4>
        <div className="rounded-md border border-border/50 p-3">
          <p className="text-sm whitespace-pre-wrap leading-relaxed">{insight.content}</p>
        </div>
      </div>

      {/* Metadata */}
      {insight.source !== "manual" && (
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <span>{insight.enrichment_task_count} enrichment task{insight.enrichment_task_count !== 1 ? "s" : ""}</span>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 pt-2 border-t border-border/50">
        <Button
          variant="outline"
          size="sm"
          className="h-8 text-xs"
          onClick={() => onNavigateToConversation(insight.conversation_id)}
        >
          <ExternalLink className="size-3 mr-1" />
          View Conversation
        </Button>
        <Button
          variant="outline"
          size="sm"
          className={`h-8 text-xs ${insight.is_bookmarked ? "text-amber-500 border-amber-500/30" : ""}`}
          onClick={() => onBookmark(insight.id, !insight.is_bookmarked)}
        >
          <Bookmark className={`size-3 mr-1 ${insight.is_bookmarked ? "fill-current" : ""}`} />
          {insight.is_bookmarked ? "Bookmarked" : "Bookmark"}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-8 text-xs text-destructive hover:text-destructive"
          onClick={() => onDelete(insight.id)}
        >
          <Trash2 className="size-3 mr-1" />
          Delete
        </Button>
      </div>

      {/* User info (admin view) */}
      {insight.user_email && (
        <div className="space-y-2">
          <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            User
          </h4>
          <span className="text-sm font-medium">{insight.user_email}</span>
        </div>
      )}
    </div>
  );
}

// ---------- Loading ----------

function InsightLoading() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-amber-500" />
    </div>
  );
}

// ---------- Empty state ----------

function InsightEmptyState({ filter }: { filter: Filter }) {
  return (
    <div className="text-center py-12">
      <Lightbulb className="size-8 text-muted-foreground mx-auto mb-2" />
      <p className="text-sm text-muted-foreground">
        {filter === "bookmarked"
          ? "No bookmarked insights"
          : filter === "manual"
            ? "No manual insights yet"
            : "No insights yet"}
      </p>
    </div>
  );
}
