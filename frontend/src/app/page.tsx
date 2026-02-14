"use client";

import { useEffect } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { ChatPanel } from "@/components/chat/chat-panel";
import { AuthGuard } from "@/components/auth/auth-guard";
import { useChatStore } from "@/stores/chat-store";

export default function Home() {
  const initFromStorage = useChatStore((s) => s.initFromStorage);

  useEffect(() => {
    initFromStorage();
  }, [initFromStorage]);

  return (
    <AuthGuard>
      <AppShell>
        <ChatPanel />
      </AppShell>
    </AuthGuard>
  );
}
