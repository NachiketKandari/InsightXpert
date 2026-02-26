"use client";

import React from "react";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { ChunkRenderer } from "@/components/chunks/chunk-renderer";
import { MessageActions } from "@/components/chat/message-actions";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useChatStore } from "@/stores/chat-store";
import type { Message } from "@/types/chat";

function MessageMetrics({ message }: { message: Message }) {
  const { generationTimeMs, inputTokens, outputTokens } = message;
  if (!generationTimeMs && !inputTokens && !outputTokens) return null;

  const timeSec = generationTimeMs != null ? (generationTimeMs / 1000).toFixed(1) : null;
  const fmt = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
  const fmtFull = (n: number) => n.toLocaleString();

  return (
    <div className="flex items-center gap-2.5 text-[11px] text-muted-foreground/60 select-none mt-0.5">
      {timeSec && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-default">{timeSec}s</span>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="text-xs">
            Generation time: {timeSec}s
          </TooltipContent>
        </Tooltip>
      )}
      {(inputTokens != null || outputTokens != null) && timeSec && (
        <span className="opacity-40">·</span>
      )}
      {inputTokens != null && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-default">↑{fmt(inputTokens)}</span>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="text-xs">
            Input tokens: {fmtFull(inputTokens)}
          </TooltipContent>
        </Tooltip>
      )}
      {inputTokens != null && outputTokens != null && (
        <span className="opacity-40">·</span>
      )}
      {outputTokens != null && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-default">↓{fmt(outputTokens)}</span>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="text-xs">
            Output tokens: {fmtFull(outputTokens)}
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}

interface MessageBubbleProps {
  message: Message;
  isLastAssistant?: boolean;
  onRetry?: () => void;
  onFeedback?: (type: "up" | "down", comment?: string) => void;
}

function MessageBubbleInner({
  message,
  isLastAssistant,
  onRetry,
  onFeedback,
}: MessageBubbleProps) {
  const isStreaming = useChatStore((s) => s.isStreaming && s.streamingConversationId === s.activeConversationId);
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
            <>
              {message.chunks.map((chunk, i) => (
                <ChunkRenderer
                  key={i}
                  chunk={chunk}
                  isComplete={
                    chunk.type === "status" || chunk.type === "tool_call" || chunk.type === "answer"
                      ? i < message.chunks.length - 1 || !isStreaming
                      : undefined
                  }
                  isStreaming={isStreaming && !!isLastAssistant}
                />
              ))}
              {isStreaming && isLastAssistant && (() => {
                const last = message.chunks[message.chunks.length - 1];
                if (last?.type === "answer" || last?.type === "error") return null;
                return (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.2 }}
                    className="flex items-center gap-2 text-sm text-muted-foreground py-1"
                  >
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-accent shrink-0" />
                    <span>Processing&hellip;</span>
                  </motion.div>
                );
              })()}
            </>
          ) : isStreaming && isLastAssistant ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-1">
              <Loader2 className="h-4 w-4 animate-spin text-cyan-accent" />
              <span>Thinking&hellip;</span>
            </div>
          ) : null}
        </div>
      )}

      {!isUser && !isStreaming && <MessageMetrics message={message} />}

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

// Note: isStreaming comes from useChatStore inside the component, so Zustand's
// subscription can trigger re-renders independently of this comparator.
// The memo prevents re-renders from parent list changes (sibling messages).
export const MessageBubble = React.memo(MessageBubbleInner, (prev, next) => {
  return (
    prev.message === next.message &&
    prev.isLastAssistant === next.isLastAssistant &&
    prev.onRetry === next.onRetry &&
    prev.onFeedback === next.onFeedback
  );
});
