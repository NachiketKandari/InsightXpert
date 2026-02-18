"use client";

import { useChatStore } from "@/stores/chat-store";
import { StepItem } from "./step-item";

export function ProcessSteps() {
  const agentSteps = useChatStore((s) => s.agentSteps);
  const isStreaming = useChatStore((s) => s.isStreaming && s.streamingConversationId === s.activeConversationId);

  if (agentSteps.length === 0 && !isStreaming) {
    return (
      <div className="px-3 py-8 text-center text-sm text-muted-foreground">
        Waiting for query...
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-0.5 p-2 overflow-hidden">
      {agentSteps.map((step) => (
        <StepItem key={step.id} step={step} />
      ))}
    </div>
  );
}
