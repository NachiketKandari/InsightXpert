"use client";

import { useHealthCheck } from "@/hooks/use-health-check";

export function HealthCheckGate({ children }: { children: React.ReactNode }) {
  useHealthCheck();
  return <>{children}</>;
}
