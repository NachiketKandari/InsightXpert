"use client";

import { useRef, useState, useCallback, useEffect, type KeyboardEvent } from "react";
import { Textarea } from "@/components/ui/textarea";
import { InputToolbar } from "./input-toolbar";
import { useChatStore } from "@/stores/chat-store";
import { useVoiceInput } from "@/hooks/use-voice-input";

interface MessageInputProps {
  onSend: (message: string) => void;
  onStop: () => void;
  isStreaming: boolean;
}

export function MessageInput({ onSend, onStop, isStreaming }: MessageInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { voiceState, voiceError, voiceText, toggleVoice, clearVoiceText } = useVoiceInput();

  // Sync voice transcript into textarea in real-time while recording
  useEffect(() => {
    if (voiceText) setValue(voiceText);
  }, [voiceText]);

  // Subscribe to pendingInput changes outside the render cycle to avoid
  // cascading setState-in-effect warnings.
  useEffect(() => {
    return useChatStore.subscribe((state) => {
      if (state.pendingInput) {
        const msg = state.pendingInput;
        state.setPendingInput(null);
        // If skipClarificationNext is set, auto-send immediately
        if (state.skipClarificationNext) {
          onSend(msg);
        } else {
          setValue(msg);
          textareaRef.current?.focus();
        }
      }
    });
  }, [onSend]);

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setValue("");
    clearVoiceText();
    textareaRef.current?.focus();
  }, [value, isStreaming, onSend, clearVoiceText]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  return (
    <div className="relative px-3 sm:px-4 pt-4 pb-3" style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}>
      {/* Gradient fade — replaces hard border-t */}
      <div className="pointer-events-none absolute inset-x-0 -top-6 h-6 bg-gradient-to-t from-background to-transparent" />
      <div className="glass-input mx-auto flex max-w-2xl flex-col rounded-2xl px-3 py-1.5">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about Indian digital payments..."
          className="min-h-[36px] max-h-[140px] flex-1 resize-none border-0 bg-transparent px-1 py-1.5 text-sm shadow-none focus-visible:ring-0"
          rows={1}
        />
        <InputToolbar
          onSend={handleSend}
          onStop={onStop}
          isStreaming={isStreaming}
          canSend={!!value.trim()}
          voiceState={voiceState}
          voiceError={voiceError}
          toggleVoice={toggleVoice}
        />
      </div>
      <p className="mx-auto mt-2 max-w-2xl text-center text-[11px] text-muted-foreground/75">
        AI can make mistakes. Please double-check responses.
      </p>
    </div>
  );
}
