"use client";

import { useCallback } from "react";
import { useChatStore } from "@/stores/chat-store";
import { useAutoScroll } from "@/hooks/use-auto-scroll";
import { MessageBubble } from "@/components/chat/message-bubble";
import { apiFetch } from "@/lib/api";

interface MessageListProps {
  onRetry?: (lastUserMessage: string) => void;
}

export function MessageList({ onRetry }: MessageListProps) {
  const conversation = useChatStore((s) => s.activeConversation());
  const messages = conversation?.messages ?? [];

  // Scroll only when the number of messages or streaming chunks changes —
  // NOT on every property update (feedback, tokens, wallTimeMs, etc.).
  const lastMsgChunkCount = messages.at(-1)?.chunks.length ?? 0;
  const { scrollRef, handleScroll } = useAutoScroll([messages.length, lastMsgChunkCount]);

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
      apiFetch("/api/feedback", {
        method: "POST",
        body: JSON.stringify({
          message_id: messageId,
          feedback: type === "up",
          comment: comment || null,
        }),
      }).catch(() => {});
    },
    []
  );

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto px-3 sm:px-4 py-4 sm:py-6"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-6">
        {messages.map((msg, idx) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              isLastAssistant={idx === lastAssistantIdx}
              onRetry={handleRetry}
              onResend={msg.role === "user" ? onRetry : undefined}
              onFeedback={handleFeedback}
            />
        ))}

      </div>
    </div>
  );
}
