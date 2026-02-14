"use client";

import { useChatStore } from "@/stores/chat-store";
import { ConversationItem } from "./conversation-item";

export function ConversationList() {
  const conversations = useChatStore((s) => s.conversations);
  const activeConversationId = useChatStore((s) => s.activeConversationId);

  if (conversations.length === 0) {
    return (
      <div className="px-3 py-8 text-center text-sm text-muted-foreground">
        No conversations yet
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-0.5 p-2">
      {conversations.map((conv) => (
        <ConversationItem
          key={conv.id}
          conversation={conv}
          isActive={conv.id === activeConversationId}
        />
      ))}
    </div>
  );
}
