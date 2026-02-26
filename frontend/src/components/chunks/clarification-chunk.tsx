"use client";

import { HelpCircle, SkipForward } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/stores/chat-store";

interface ClarificationChunkProps {
  content: string;
  skipAllowed?: boolean;
}

export function ClarificationChunk({
  content,
  skipAllowed = true,
}: ClarificationChunkProps) {
  const { isStreaming, pendingClarification } = useChatStore();

  const handleSkip = () => {
    const store = useChatStore.getState();
    // Find the last user message to re-send
    const conv = store.activeConversation();
    const lastUserMsg = conv?.messages
      .filter((m) => m.role === "user")
      .pop();

    if (lastUserMsg) {
      store.setSkipClarificationNext(true);
      store.setPendingClarification(null);
      // Set pending input so the chat input component picks it up and sends
      store.setPendingInput(lastUserMsg.content);
    }
  };

  // Only show skip button if this is the latest clarification and not currently streaming
  const showSkip = skipAllowed && pendingClarification && !isStreaming;

  return (
    <Card className="border-l-4 border-l-amber-500 border-amber-200/50 bg-amber-50/50 dark:bg-amber-950/20 dark:border-amber-800/50">
      <CardContent className="py-3">
        <div className="flex items-start gap-3">
          <HelpCircle className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
          <div className="flex-1 space-y-2">
            <p className="text-sm text-amber-900 dark:text-amber-200">{content}</p>
            {showSkip && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs text-amber-700 dark:text-amber-300 hover:text-amber-900 dark:hover:text-amber-100 hover:bg-amber-100 dark:hover:bg-amber-900/40"
                onClick={handleSkip}
              >
                <SkipForward className="h-3 w-3 mr-1" />
                Just answer with best guess
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
