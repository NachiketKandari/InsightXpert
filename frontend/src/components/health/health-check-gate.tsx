"use client";

import { useHealthCheck } from "@/hooks/use-health-check";
import { ServerDownScreen } from "./server-down-screen";

export function HealthCheckGate({ children }: { children: React.ReactNode }) {
  const { status, lastChecked, retry } = useHealthCheck();

  // Show the down screen if unhealthy, or if we're re-checking after a known failure
  const showDownScreen =
    status === "unhealthy" || (status === "checking" && lastChecked !== null);

  return (
    <>
      {children}
      {showDownScreen && (
        <ServerDownScreen status={status} lastChecked={lastChecked} onRetry={retry} />
      )}
    </>
  );
}
