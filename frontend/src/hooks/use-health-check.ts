"use client";

import { useEffect } from "react";
import { API_BASE_URL } from "@/lib/constants";

const TIMEOUT_MS      = 3_000;
const HEALTHY_POLL_MS = 30_000;

/** Polls /api/health with exponential backoff. On failure, redirects to the static 503 page. */
export function useHealthCheck() {
  useEffect(() => {
    let pollId: ReturnType<typeof setTimeout>;
    let cancelled = false;
    let interval = HEALTHY_POLL_MS;

    const check = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/health`, {
          signal: AbortSignal.timeout(TIMEOUT_MS),
          cache: "no-store",
        });
        if (res.ok) {
          if (!cancelled) {
            interval = Math.min(interval * 2, 120_000);
            pollId = setTimeout(check, interval);
          }
          return;
        }
      } catch { /* fall through */ }

      if (!cancelled) {
        // Reset to fast polling on error before redirecting
        interval = HEALTHY_POLL_MS;
        try { sessionStorage.setItem("503-return", location.pathname + location.search); } catch { /* */ }
        location.href = "/503.html";
      }
    };

    pollId = setTimeout(check, 0);
    return () => { cancelled = true; clearTimeout(pollId); };
  }, []);
}
