"use client";

import { useEffect } from "react";

const TIMEOUT_MS      = 3_000;
const HEALTHY_POLL_MS = 30_000;

/** Polls /api/health. On failure, redirects to the static 503 page. */
export function useHealthCheck() {
  useEffect(() => {
    let pollId: ReturnType<typeof setTimeout>;
    let cancelled = false;

    const check = async () => {
      try {
        const res = await fetch("/api/health", {
          signal: AbortSignal.timeout(TIMEOUT_MS),
          cache: "no-store",
        });
        if (res.ok) {
          if (!cancelled) pollId = setTimeout(check, HEALTHY_POLL_MS);
          return;
        }
      } catch { /* fall through */ }

      if (!cancelled) {
        try { sessionStorage.setItem("503-return", location.pathname + location.search); } catch { /* */ }
        location.href = "/503.html";
      }
    };

    pollId = setTimeout(check, 0);
    return () => { cancelled = true; clearTimeout(pollId); };
  }, []);
}
