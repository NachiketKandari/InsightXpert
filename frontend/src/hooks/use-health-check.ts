"use client";

import { useEffect } from "react";
import { API_BASE_URL } from "@/lib/constants";

const TIMEOUT_MS = 30_000;
const MAX_ATTEMPTS = 6;
const BACKOFF_MS = [0, 2_000, 4_000, 8_000, 15_000, 25_000];

/**
 * One-shot backend reachability check on mount. Retries with backoff to absorb
 * Cloud Run cold starts (~20s while the libSQL embedded replica syncs). On
 * persistent failure, redirects to the static 503 page. Does NOT poll on
 * success — that would defeat scale-to-zero by keeping the instance warm.
 */
export function useHealthCheck() {
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const attempt = async (n: number): Promise<void> => {
      if (cancelled) return;
      try {
        const res = await fetch(`${API_BASE_URL}/api/health`, {
          signal: AbortSignal.timeout(TIMEOUT_MS),
          cache: "no-store",
        });
        if (res.ok) return;
      } catch { /* fall through */ }

      if (cancelled) return;
      if (n + 1 >= MAX_ATTEMPTS) {
        try { sessionStorage.setItem("503-return", location.pathname + location.search); } catch { /* */ }
        location.href = "/503.html";
        return;
      }
      timer = setTimeout(() => attempt(n + 1), BACKOFF_MS[n + 1]);
    };

    timer = setTimeout(() => attempt(0), 0);
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, []);
}
