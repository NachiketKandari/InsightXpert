"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Lightbulb } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useInsightStore } from "@/stores/insight-store";
import { InsightPopover } from "./insight-popover";
import { InsightAllModal } from "./insight-all-modal";

export function InsightBell() {
  const totalCount = useInsightStore((s) => s.totalCount);
  const fetchCount = useInsightStore((s) => s.fetchCount);
  const fetchInsights = useInsightStore((s) => s.fetchInsights);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Poll count every 60s
  useEffect(() => {
    fetchCount();
    const interval = setInterval(fetchCount, 60_000);
    return () => clearInterval(interval);
  }, [fetchCount]);

  // Fetch insights when popover opens
  const handleToggle = useCallback(() => {
    setPopoverOpen((prev) => {
      if (!prev) fetchInsights();
      return !prev;
    });
  }, [fetchInsights]);

  // Close on outside click
  useEffect(() => {
    if (!popoverOpen) return;
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setPopoverOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [popoverOpen]);

  const handleShowAll = useCallback(() => {
    setPopoverOpen(false);
    setModalOpen(true);
  }, []);

  return (
    <>
      <div className="relative" ref={popoverRef}>
        <Button
          variant="ghost"
          size="icon"
          className="size-9 relative"
          onClick={handleToggle}
          aria-label="Insights"
        >
          <Lightbulb className="size-4.5" />
          {totalCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center size-4 rounded-full bg-amber-500 text-[10px] font-medium text-white">
              {totalCount > 9 ? "9+" : totalCount}
            </span>
          )}
        </Button>

        {popoverOpen && (
          <div className="absolute right-0 top-full mt-1 z-50">
            <InsightPopover onShowAll={handleShowAll} />
          </div>
        )}
      </div>

      <InsightAllModal open={modalOpen} onOpenChange={setModalOpen} />
    </>
  );
}
