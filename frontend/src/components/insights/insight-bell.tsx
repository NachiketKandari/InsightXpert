"use client";

import { useState, useCallback } from "react";
import { Lightbulb } from "lucide-react";
import { useInsightStore } from "@/stores/insight-store";
import { HeaderBell } from "@/components/ui/header-bell";
import { InsightPopover } from "./insight-popover";
import { InsightAllModal } from "./insight-all-modal";
import type { Insight } from "@/types/insight";

export function InsightBell() {
  const totalCount = useInsightStore((s) => s.totalCount);
  const fetchCount = useInsightStore((s) => s.fetchCount);
  const fetchInsights = useInsightStore((s) => s.fetchInsights);
  const [initialInsight, setInitialInsight] = useState<Insight | null>(null);

  const handleSelectInsight = useCallback((insight: Insight, showAll: () => void) => {
    setInitialInsight(insight);
    showAll();
  }, []);

  return (
    <HeaderBell
      icon={<Lightbulb className="size-4.5" />}
      count={totalCount}
      badgeClassName="bg-amber-500"
      label="Insights"
      pollIntervalMs={60_000}
      onPoll={fetchCount}
      onOpen={fetchInsights}
      renderPopover={({ showAll }) => (
        <InsightPopover
          onShowAll={() => { setInitialInsight(null); showAll(); }}
          onSelectInsight={(insight) => handleSelectInsight(insight, showAll)}
        />
      )}
      renderModal={(open, onOpenChange) => (
        <InsightAllModal open={open} onOpenChange={onOpenChange} initialInsight={initialInsight} />
      )}
    />
  );
}
