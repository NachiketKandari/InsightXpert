"use client";

import { useCallback } from "react";
import { useSSEChat } from "@/hooks/use-sse-chat";
import { useChatStore } from "@/stores/chat-store";
import { useSettingsStore } from "@/stores/settings-store";
import { WelcomeScreen } from "@/components/chat/welcome-screen";
import { MessageList } from "@/components/chat/message-list";
import { MessageInput } from "@/components/chat/message-input";

export function ChatPanel() {
  const { sendMessage, sendInvestigation, stopStreaming, isStreaming } = useSSEChat();
  const agentMode = useSettingsStore((s) => s.agentMode);
  const conversation = useChatStore((s) => s.activeConversation());
  const isLoadingConversation = useChatStore((s) => s.isLoadingConversation);
  const hasMessages = conversation && conversation.messages.length > 0;

  const handleSend = useCallback(
    (message: string) => {
      if (message === "__INVESTIGATE__") {
        const investigation = useChatStore.getState().pendingInvestigation;
        if (investigation) {
          sendInvestigation(investigation, agentMode);
          return;
        }
      }
      sendMessage(message, agentMode);
    },
    [sendMessage, sendInvestigation, agentMode],
  );

  return (
    <div className="flex h-full flex-col">
      {isLoadingConversation ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-foreground" />
        </div>
      ) : hasMessages ? (
        <>
          <MessageList onRetry={handleSend} />
          <MessageInput
            onSend={handleSend}
            onStop={stopStreaming}
            isStreaming={isStreaming}
          />
        </>
      ) : (
        <WelcomeScreen
          onSendMessage={handleSend}
          onStop={stopStreaming}
          isStreaming={isStreaming}
        />
      )}
    </div>
  );
}
