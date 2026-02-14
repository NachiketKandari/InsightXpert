"use client";

import { useState, useRef, useEffect } from "react";
import { MoreHorizontal, Pencil, Trash2, MessageSquare, Check, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { useChatStore } from "@/stores/chat-store";
import type { Conversation } from "@/types/chat";
import { cn } from "@/lib/utils";

interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
}

function relativeTime(timestamp: number): string {
  const diff = Date.now() - timestamp;
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function ConversationItem({
  conversation,
  isActive,
}: ConversationItemProps) {
  const setActiveConversation = useChatStore((s) => s.setActiveConversation);
  const deleteConversation = useChatStore((s) => s.deleteConversation);
  const renameConversation = useChatStore((s) => s.renameConversation);

  const [isRenaming, setIsRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(conversation.title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isRenaming && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isRenaming]);

  const handleConfirmRename = () => {
    const trimmed = renameValue.trim();
    if (trimmed && trimmed !== conversation.title) {
      renameConversation(conversation.id, trimmed);
    }
    setIsRenaming(false);
  };

  const handleCancelRename = () => {
    setRenameValue(conversation.title);
    setIsRenaming(false);
  };

  const handleRenameKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleConfirmRename();
    } else if (e.key === "Escape") {
      handleCancelRename();
    }
  };

  if (isRenaming) {
    return (
      <div className="flex items-center gap-1.5 w-full rounded-md px-2 py-1.5 bg-accent">
        <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
        <Input
          ref={inputRef}
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onKeyDown={handleRenameKeyDown}
          onBlur={handleConfirmRename}
          className="h-6 text-sm px-1.5 py-0 border-primary/50"
        />
        <button
          type="button"
          className="inline-flex items-center justify-center size-5 rounded-md shrink-0 hover:bg-accent-foreground/10"
          onClick={handleConfirmRename}
          title="Confirm"
        >
          <Check className="size-3 text-emerald-500" />
        </button>
        <button
          type="button"
          className="inline-flex items-center justify-center size-5 rounded-md shrink-0 hover:bg-accent-foreground/10"
          onClick={handleCancelRename}
          title="Cancel"
        >
          <X className="size-3 text-muted-foreground" />
        </button>
      </div>
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => setActiveConversation(conversation.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") setActiveConversation(conversation.id);
      }}
      className={cn(
        "group flex items-center gap-2 w-full rounded-md px-2.5 py-2 text-left transition-colors cursor-pointer",
        "hover:bg-accent/50",
        isActive && "bg-accent/60 border-l-2 border-cyan-accent"
      )}
    >
      <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
      <div className="flex-1 min-w-0">
        <p className="text-sm truncate" title={conversation.title}>
          {conversation.title}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5 truncate">
          {relativeTime(conversation.updatedAt)}
        </p>
      </div>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className={cn(
              "inline-flex items-center justify-center size-7 rounded-md shrink-0",
              "text-muted-foreground hover:text-foreground hover:bg-accent-foreground/10",
              "opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-all"
            )}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            <MoreHorizontal className="size-4" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-36">
          <DropdownMenuItem
            onClick={(e) => {
              e.stopPropagation();
              setRenameValue(conversation.title);
              setIsRenaming(true);
            }}
          >
            <Pencil className="size-4" />
            Rename
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            onClick={(e) => {
              e.stopPropagation();
              deleteConversation(conversation.id);
            }}
          >
            <Trash2 className="size-4" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
