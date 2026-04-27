"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/constants";

const TIMEOUT_MS = 30_000;
const MAX_ATTEMPTS = 6;
const BACKOFF_MS = [0, 2_000, 4_000, 8_000, 15_000, 25_000];
const COLD_START_HINT_MS = 2_500; // show overlay after this much "still checking"

export type HealthStatus = "checking" | "ready" | "failed";

/**
 * One-shot backend reachability check on mount with exponential backoff to
 * absorb Cloud Run cold starts (~20s while libSQL embedded replica syncs).
 *
 * Returns:
 *   - status: 'checking' until the first successful probe, then 'ready'
 *   - showColdStartHint: true when checking has gone on long enough that
 *     the consumer should render a "waking up" overlay
 *
 * On persistent failure, redirects to the static 503 page. Does NOT poll on
 * success — that would defeat scale-to-zero by keeping the instance warm.
 */
export function useHealthCheck(): { status: HealthStatus; showColdStartHint: boolean } {
  const [status, setStatus] = useState<HealthStatus>("checking");
  const [showColdStartHint, setShowColdStartHint] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let attemptTimer: ReturnType<typeof setTimeout> | undefined;
    let hintTimer: ReturnType<typeof setTimeout> | undefined;

    // Show the cold-start overlay if the first probe doesn't return quickly.
    hintTimer = setTimeout(() => {
      if (!cancelled) setShowColdStartHint(true);
    }, COLD_START_HINT_MS);

    const attempt = async (n: number): Promise<void> => {
      if (cancelled) return;
      try {
        const res = await fetch(`${API_BASE_URL}/api/health`, {
          signal: AbortSignal.timeout(TIMEOUT_MS),
          cache: "no-store",
        });
        if (res.ok) {
          if (!cancelled) {
            if (hintTimer) clearTimeout(hintTimer);
            setStatus("ready");
            setShowColdStartHint(false);
          }
          return;
        }
      } catch { /* fall through */ }

      if (cancelled) return;
      if (n + 1 >= MAX_ATTEMPTS) {
        setStatus("failed");
        try { sessionStorage.setItem("503-return", location.pathname + location.search); } catch { /* */ }
        location.href = "/503.html";
        return;
      }
      // After the first failure, definitely show the cold-start hint.
      setShowColdStartHint(true);
      attemptTimer = setTimeout(() => attempt(n + 1), BACKOFF_MS[n + 1]);
    };

    attemptTimer = setTimeout(() => attempt(0), 0);
    return () => {
      cancelled = true;
      if (attemptTimer) clearTimeout(attemptTimer);
      if (hintTimer) clearTimeout(hintTimer);
    };
  }, []);

  return { status, showColdStartHint };
}
