"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useClientConfig } from "@/hooks/use-client-config";
import { AuthGuard } from "@/components/auth/auth-guard";

function AdminGuard({ children }: { children: React.ReactNode }) {
  const { isAdmin, isLoading, fetchConfig } = useClientConfig();
  const router = useRouter();

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  useEffect(() => {
    if (!isLoading && !isAdmin) {
      router.push("/");
    }
  }, [isLoading, isAdmin, router]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (!isAdmin) return null;

  return <>{children}</>;
}

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <AdminGuard>{children}</AdminGuard>
    </AuthGuard>
  );
}
