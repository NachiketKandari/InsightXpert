"use client";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ChunkRenderer } from "@/components/chunks/chunk-renderer";
import { ThumbsUp, ThumbsDown, MessageSquare, ChevronLeft, ChevronRight } from "lucide-react";
import type { ChatChunk } from "@/types/chat";

interface ConversationMessage {
  id: string;
  role: string;
  content: string;
  chunks: ChatChunk[] | null;
  feedback?: boolean | null;
  feedback_comment?: string | null;
  created_at: string;
}

interface ConversationData {
  id: string;
  title: string;
  is_starred: boolean;
  messages: ConversationMessage[];
  created_at: string;
  updated_at: string;
}

interface ConversationViewerProps {
  conversation: ConversationData | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentIndex: number;
  totalCount: number;
  onPrev: () => void;
  onNext: () => void;
}

export function ConversationViewer({
  conversation,
  open,
  onOpenChange,
  currentIndex,
  totalCount,
  onPrev,
  onNext,
}: ConversationViewerProps) {
  if (!conversation) return null;

  const msgCount = conversation.messages.length;
  const userMsgCount = conversation.messages.filter((m) => m.role === "user").length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-4xl max-h-[85vh] flex flex-col p-0">
        <DialogHeader className="px-6 pt-5 pb-3 border-b border-border shrink-0">
          <div className="flex items-center gap-2 pr-8">
            <DialogTitle className="text-base truncate flex-1">
              {conversation.title}
            </DialogTitle>
            {totalCount > 1 && (
              <div className="flex items-center gap-1 shrink-0">
                <Button variant="ghost" size="icon" className="size-7" onClick={onPrev}>
                  <ChevronLeft className="size-4" />
                </Button>
                <span className="text-xs text-muted-foreground tabular-nums min-w-[3ch] text-center">
                  {currentIndex + 1}/{totalCount}
                </span>
                <Button variant="ghost" size="icon" className="size-7" onClick={onNext}>
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            )}
          </div>
          <DialogDescription className="flex items-center gap-3 text-xs">
            <span>{userMsgCount} question{userMsgCount !== 1 ? "s" : ""}, {msgCount} message{msgCount !== 1 ? "s" : ""}</span>
            <span>Started {new Date(conversation.created_at).toLocaleString()}</span>
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {conversation.messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
            >
              {msg.role === "user" ? (
                <div className="max-w-[90%] sm:max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-3 sm:px-4 py-2 sm:py-2.5 text-sm text-primary-foreground">
                  {msg.content}
                </div>
              ) : (
                <div className="w-full space-y-3">
                  {msg.chunks && msg.chunks.length > 0 ? (
                    msg.chunks.map((chunk, i) => (
                      <ChunkRenderer key={i} chunk={chunk} isComplete={true} />
                    ))
                  ) : (
                    <div className="text-sm text-foreground whitespace-pre-wrap">
                      {msg.content}
                    </div>
                  )}
                </div>
              )}

              {/* Feedback indicator (read-only) */}
              {msg.role === "assistant" && msg.feedback !== null && msg.feedback !== undefined && (
                <div className="flex items-center gap-1.5 mt-1 text-xs text-muted-foreground">
                  {msg.feedback ? (
                    <ThumbsUp className="size-3 text-emerald-500" />
                  ) : (
                    <ThumbsDown className="size-3 text-red-400" />
                  )}
                  {msg.feedback_comment && (
                    <span className="italic truncate max-w-[200px]">
                      &quot;{msg.feedback_comment}&quot;
                    </span>
                  )}
                </div>
              )}
            </div>
          ))}

          {conversation.messages.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <MessageSquare className="size-8 mb-2 opacity-50" />
              <p className="text-sm">No messages in this conversation</p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
