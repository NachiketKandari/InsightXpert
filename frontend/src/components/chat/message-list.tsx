"use client";

import { useChatStore } from "@/stores/chat-store";
import { useAutoScroll } from "@/hooks/use-auto-scroll";
import { MessageBubble } from "@/components/chat/message-bubble";
import { Skeleton } from "@/components/ui/skeleton";

export function MessageList() {
  const conversation = useChatStore((s) => s.activeConversation());
  const isStreaming = useChatStore((s) => s.isStreaming);
  const messages = conversation?.messages ?? [];

  const { scrollRef, handleScroll } = useAutoScroll([messages]);

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto px-4 py-6"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-6">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {isStreaming &&
          messages.length > 0 &&
          messages[messages.length - 1].role === "assistant" &&
          messages[messages.length - 1].chunks.length === 0 && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Skeleton className="h-2 w-2 rounded-full" />
              <Skeleton className="h-2 w-2 rounded-full" />
              <Skeleton className="h-2 w-2 rounded-full" />
            </div>
          )}
      </div>
    </div>
  );
}
