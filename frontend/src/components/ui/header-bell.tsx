"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface HeaderBellProps {
  icon: React.ReactNode;
  count: number;
  badgeClassName?: string;
  label: string;
  pollIntervalMs: number;
  onPoll: () => void;
  onOpen: () => void;
  renderPopover: (controls: { showAll: () => void }) => React.ReactNode;
  renderModal: (open: boolean, onOpenChange: (open: boolean) => void) => React.ReactNode;
}

export function HeaderBell({
  icon,
  count,
  badgeClassName = "bg-destructive",
  label,
  pollIntervalMs,
  onPoll,
  onOpen,
  renderPopover,
  renderModal,
}: HeaderBellProps) {
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Poll on interval
  useEffect(() => {
    onPoll();
    const interval = setInterval(onPoll, pollIntervalMs);
    return () => clearInterval(interval);
  }, [onPoll, pollIntervalMs]);

  // Toggle popover; fetch data when opening
  const handleToggle = useCallback(() => {
    setPopoverOpen((prev) => {
      if (!prev) onOpen();
      return !prev;
    });
  }, [onOpen]);

  // Close popover on outside click
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

  // Transition from popover → modal
  const showAll = useCallback(() => {
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
          aria-label={label}
        >
          {icon}
          {count > 0 && (
            <span
              className={cn(
                "absolute -top-0.5 -right-0.5 flex items-center justify-center size-4 rounded-full text-[10px] font-medium text-white",
                badgeClassName,
              )}
            >
              {count > 9 ? "9+" : count}
            </span>
          )}
        </Button>

        {popoverOpen && (
          <div className="absolute right-0 top-full mt-1 z-50">
            {renderPopover({ showAll })}
          </div>
        )}
      </div>

      {renderModal(modalOpen, setModalOpen)}
    </>
  );
}
