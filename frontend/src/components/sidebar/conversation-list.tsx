"use client";

import { useMemo } from "react";
import { useChatStore } from "@/stores/chat-store";
import { ConversationItem } from "./conversation-item";
import type { Conversation } from "@/types/chat";

interface ConversationGroup {
  label: string;
  conversations: Conversation[];
}

function groupConversationsByDate(conversations: Conversation[]): ConversationGroup[] {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();

  const groups: Record<string, Conversation[]> = {
    Today: [],
    Older: [],
  };

  // Sort by updatedAt descending first
  const sorted = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt);

  for (const conv of sorted) {
    if (conv.updatedAt >= startOfToday) {
      groups["Today"].push(conv);
    } else {
      groups["Older"].push(conv);
    }
  }

  // Return only non-empty groups in order
  const orderedLabels = ["Today", "Older"];
  return orderedLabels
    .filter((label) => groups[label].length > 0)
    .map((label) => ({ label, conversations: groups[label] }));
}

export function ConversationList() {
  const conversations = useChatStore((s) => s.conversations);
  const activeConversationId = useChatStore((s) => s.activeConversationId);

  const groups = useMemo(() => groupConversationsByDate(conversations), [conversations]);

  if (conversations.length === 0) {
    return (
      <div className="px-3 py-8 text-center text-sm text-muted-foreground">
        No conversations yet
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-2">
      {groups.map((group) => (
        <div key={group.label}>
          <p className="px-2.5 pb-1 text-xs font-medium text-muted-foreground uppercase tracking-wider">
            {group.label}
          </p>
          <div className="flex flex-col gap-0.5">
            {group.conversations.map((conv) => (
              <ConversationItem
                key={conv.id}
                conversation={conv}
                isActive={conv.id === activeConversationId}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
