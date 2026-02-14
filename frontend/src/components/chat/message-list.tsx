"use client";

import { useCallback } from "react";
import { useChatStore } from "@/stores/chat-store";
import { useAutoScroll } from "@/hooks/use-auto-scroll";
import { MessageBubble } from "@/components/chat/message-bubble";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";

interface MessageListProps {
  onRetry?: (lastUserMessage: string) => void;
}

export function MessageList({ onRetry }: MessageListProps) {
  const conversation = useChatStore((s) => s.activeConversation());
  const isStreaming = useChatStore((s) => s.isStreaming);
  const messages = conversation?.messages ?? [];

  const { scrollRef, handleScroll } = useAutoScroll([messages]);

  // Find the last user message for retry
  const lastUserMessage = [...messages].reverse().find((m) => m.role === "user");

  // Find the last assistant message index
  const lastAssistantIdx = messages.reduce(
    (acc, msg, idx) => (msg.role === "assistant" ? idx : acc),
    -1
  );

  const handleRetry = useCallback(() => {
    if (lastUserMessage && onRetry) {
      onRetry(lastUserMessage.content);
    }
  }, [lastUserMessage, onRetry]);

  const handleFeedback = useCallback(
    (messageId: string, type: "up" | "down", comment?: string) => {
      const conversationId = conversation?.id;
      if (!conversationId) return;
      apiFetch("/api/feedback", {
        method: "POST",
        body: JSON.stringify({
          conversation_id: conversationId,
          message_id: messageId,
          rating: type,
          comment: comment || "",
        }),
      }).catch(() => {});
    },
    [conversation?.id]
  );

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto px-4 py-6"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-6">
        {messages.map((msg, idx) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            isLastAssistant={idx === lastAssistantIdx}
            onRetry={handleRetry}
            onFeedback={(type, comment) =>
              handleFeedback(msg.id, type, comment)
            }
          />
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
