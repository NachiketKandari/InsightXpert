"use client";

import { useHealthCheck } from "@/hooks/use-health-check";
import { ColdStartScreen } from "@/components/health/cold-start-screen";

export function HealthCheckGate({ children }: { children: React.ReactNode }) {
  const { status, showColdStartHint } = useHealthCheck();
  // Render the app underneath so it's mounted and ready to fade in once
  // health passes; overlay sits on top while we wait for the first 200.
  return (
    <>
      {children}
      {status === "checking" && showColdStartHint && <ColdStartScreen />}
    </>
  );
}
