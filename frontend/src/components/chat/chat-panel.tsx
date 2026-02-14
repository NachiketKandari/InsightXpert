"use client";

import { useSSEChat } from "@/hooks/use-sse-chat";
import { useChatStore } from "@/stores/chat-store";
import { WelcomeScreen } from "@/components/chat/welcome-screen";
import { MessageList } from "@/components/chat/message-list";
import { MessageInput } from "@/components/chat/message-input";

export function ChatPanel() {
  const { sendMessage, stopStreaming, isStreaming } = useSSEChat();
  const conversation = useChatStore((s) => s.activeConversation());
  const hasMessages = conversation && conversation.messages.length > 0;

  return (
    <div className="flex h-full flex-col">
      {hasMessages ? (
        <>
          <MessageList onRetry={sendMessage} />
          <MessageInput
            onSend={sendMessage}
            onStop={stopStreaming}
            isStreaming={isStreaming}
          />
        </>
      ) : (
        <>
          <WelcomeScreen onSendMessage={sendMessage} />
          <MessageInput
            onSend={sendMessage}
            onStop={stopStreaming}
            isStreaming={isStreaming}
          />
        </>
      )}
    </div>
  );
}
