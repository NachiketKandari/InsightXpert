"use client";

import { useEffect } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { ChatPanel } from "@/components/chat/chat-panel";
import { AuthGuard } from "@/components/auth/auth-guard";
import { useChatStore } from "@/stores/chat-store";
import { useClientConfigStore } from "@/stores/client-config-store";

function AuthenticatedApp() {
  const initFromStorage = useChatStore((s) => s.initFromStorage);
  const fetchConfig = useClientConfigStore((s) => s.fetchConfig);

  useEffect(() => {
    initFromStorage();
    fetchConfig();
  }, [initFromStorage, fetchConfig]);

  return (
    <AppShell>
      <ChatPanel />
    </AppShell>
  );
}

export default function Home() {
  return (
    <AuthGuard>
      <AuthenticatedApp />
    </AuthGuard>
  );
}
