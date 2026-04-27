"use client";

import { useEffect, useState } from "react";

const TYPICAL_COLD_START_SECONDS = 25;

/**
 * Full-screen overlay shown while the backend is cold-starting on Cloud Run.
 * Embedded libSQL replica clone + ChromaDB warmup + Python imports add up to
 * roughly 20-25 seconds on the first request after the instance scales to
 * zero. Beats throwing the user into a frozen app or a 503 page.
 */
export function ColdStartScreen() {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const progress = Math.min(100, (elapsed / TYPICAL_COLD_START_SECONDS) * 100);
  const overdue = elapsed > TYPICAL_COLD_START_SECONDS + 10;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background p-6">
      <div className="flex w-full max-w-md flex-col items-center gap-7 text-center animate-in fade-in slide-in-from-bottom-4 duration-500">
        {/* Animated logo / pulse */}
        <div className="relative h-20 w-20">
          <div className="absolute inset-0 rounded-full bg-primary/20 animate-ping" />
          <div className="absolute inset-2 rounded-full bg-primary/30 animate-pulse" />
          <div className="absolute inset-4 rounded-full bg-primary flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6 text-primary-foreground">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
            </svg>
          </div>
        </div>

        {/* Heading + copy */}
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">
            Waking up the server
          </h1>
          <p className="text-sm text-muted-foreground leading-relaxed">
            InsightXpert runs on a free-tier backend that scales to zero when
            idle to keep this project free. The first request after a quiet
            period takes about <span className="font-medium text-foreground">{TYPICAL_COLD_START_SECONDS} seconds</span> while
            the server boots and the database replica syncs.
          </p>
        </div>

        {/* Progress bar */}
        <div className="w-full space-y-2">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full bg-primary transition-all duration-1000 ease-linear"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
            <span>{elapsed}s elapsed</span>
            <span>~{TYPICAL_COLD_START_SECONDS}s typical</span>
          </div>
        </div>

        {/* Overdue hint */}
        {overdue && (
          <p className="text-xs text-muted-foreground/80 italic max-w-sm">
            Taking longer than usual — the server may be doing first-time
            setup. We&apos;ll keep retrying.
          </p>
        )}

        {/* Tiny footer */}
        <p className="text-[11px] text-muted-foreground/60">
          You won&apos;t see this again once the server is warm.
        </p>
      </div>
    </div>
  );
}
