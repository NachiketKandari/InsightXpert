"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/constants";

export type HealthStatus = "checking" | "healthy" | "unhealthy";

export interface UseHealthCheckResult {
  status: HealthStatus;
  lastChecked: Date | null;
  retry: () => void;
}

const UNHEALTHY_POLL_MS = 10_000;
const HEALTHY_POLL_MS = 30_000;
const TIMEOUT_MS = 3_000;

export function useHealthCheck(): UseHealthCheckResult {
  const [status, setStatus] = useState<HealthStatus>("checking");
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const check = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/health`, {
        signal: AbortSignal.timeout(TIMEOUT_MS),
        cache: "no-store",
      });
      if (res.ok) {
        setStatus("healthy");
        setLastChecked(new Date());
        return;
      }
    } catch {
      // network error or timeout — fall through to unhealthy
    }
    setStatus("unhealthy");
    setLastChecked(new Date());
  }, []);

  // Initial check on mount
  useEffect(() => {
    check();
  }, [check]);

  // Continuous polling: 10s when unhealthy, 30s when healthy
  useEffect(() => {
    const interval = status === "unhealthy" ? UNHEALTHY_POLL_MS : HEALTHY_POLL_MS;
    const id = setInterval(check, interval);
    return () => clearInterval(id);
  }, [status, check]);

  const retry = useCallback(() => {
    setStatus("checking");
    check();
  }, [check]);

  return { status, lastChecked, retry };
}
