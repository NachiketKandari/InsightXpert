"use client";

import { AuthGuard } from "@/components/auth/auth-guard";

export default function ConnectionsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AuthGuard>{children}</AuthGuard>;
}
