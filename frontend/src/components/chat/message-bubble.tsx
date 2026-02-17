"use client";

import { motion } from "framer-motion";
import { Skeleton } from "@/components/ui/skeleton";
import { ChunkRenderer } from "@/components/chunks/chunk-renderer";
import { MessageActions } from "@/components/chat/message-actions";
import { useChatStore } from "@/stores/chat-store";
import type { Message } from "@/types/chat";

interface MessageBubbleProps {
  message: Message;
  isLastAssistant?: boolean;
  onRetry?: () => void;
  onFeedback?: (type: "up" | "down", comment?: string) => void;
}

export function MessageBubble({
  message,
  isLastAssistant,
  onRetry,
  onFeedback,
}: MessageBubbleProps) {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className={`group/message flex flex-col ${isUser ? "items-end" : "items-start"}`}
    >
      {isUser ? (
        <div className="max-w-[90%] sm:max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-3 sm:px-4 py-2 sm:py-2.5 text-sm text-primary-foreground">
          {message.content}
        </div>
      ) : (
        <div className="w-full space-y-3">
          {message.chunks.length > 0 ? (
            message.chunks.map((chunk, i) => (
              <ChunkRenderer
                key={i}
                chunk={chunk}
                isComplete={
                  chunk.type === "status" || chunk.type === "tool_call" || chunk.type === "answer"
                    ? i < message.chunks.length - 1 || !isStreaming
                    : undefined
                }
              />
            ))
          ) : (
            <div className="space-y-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          )}
        </div>
      )}

      {message.content && (
        <MessageActions
          role={message.role}
          content={message.content}
          isLastAssistant={isLastAssistant}
          onRetry={onRetry}
          onFeedback={onFeedback}
        />
      )}
    </motion.div>
  );
}
