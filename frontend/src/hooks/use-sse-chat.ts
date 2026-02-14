"use client";

import { useCallback, useRef } from "react";
import { useChatStore } from "@/stores/chat-store";
import { createSSEStream } from "@/lib/sse-client";
import { parseChunk } from "@/lib/chunk-parser";
import type { AgentStep } from "@/types/chat";

function generateStepId() {
  return Math.random().toString(36).slice(2, 8);
}

export function useSSEChat() {
  const abortRef = useRef<AbortController | null>(null);

  const {
    activeConversationId,
    isStreaming,
    addUserMessage,
    startAssistantMessage,
    appendChunk,
    finishStreaming,
    addAgentStep,
    updateAgentStep,
    clearAgentSteps,
    newConversation,
  } = useChatStore();

  const sendMessage = useCallback(
    (message: string) => {
      if (isStreaming) return;

      let convId = activeConversationId;
      if (!convId) {
        convId = newConversation();
      }

      addUserMessage(message);
      startAssistantMessage();
      clearAgentSteps();

      // Track the last step that has status "running" so we can mark it
      // "done" as soon as the next chunk arrives (regardless of type).
      let lastRunningStepId: string | null = null;

      const markLastRunningDone = () => {
        if (lastRunningStepId) {
          updateAgentStep(lastRunningStepId, { status: "done" });
          lastRunningStepId = null;
        }
      };

      const controller = createSSEStream(message, convId, {
        onChunk: (raw) => {
          const chunk = parseChunk(raw);
          if (!chunk) return;

          appendChunk(chunk);

          // Update agent step timeline.
          // Only mark the previous running step as done when a NEW phase
          // begins (status, tool_call, tool_result, answer, error).
          // The "sql" chunk is a detail update on the current step, so it
          // must NOT mark the previous step done.
          if (chunk.type === "status") {
            markLastRunningDone();
            const stepId = generateStepId();
            const step: AgentStep = {
              id: stepId,
              label: chunk.content || "Processing...",
              status: "running",
              timestamp: chunk.timestamp,
            };
            addAgentStep(step);
            lastRunningStepId = stepId;
          } else if (chunk.type === "tool_call") {
            markLastRunningDone();
            const stepId = generateStepId();
            const step: AgentStep = {
              id: stepId,
              label: chunk.content || "Calling tool...",
              status: "running",
              detail: chunk.sql || undefined,
              sql: chunk.sql || undefined,
              toolName: chunk.tool_name || undefined,
              toolArgs: chunk.args || undefined,
              llmReasoning: (chunk.data?.llm_reasoning as string) || undefined,
              timestamp: chunk.timestamp,
            };
            addAgentStep(step);
            lastRunningStepId = stepId;
          } else if (chunk.type === "sql") {
            // Merge SQL into the existing tool_call step instead of creating
            // a separate step. Do NOT call markLastRunningDone() here — the
            // tool_call step should stay "running" until the next phase.
            if (lastRunningStepId) {
              updateAgentStep(lastRunningStepId, {
                detail: chunk.sql || undefined,
                sql: chunk.sql || undefined,
              });
            }
          } else if (chunk.type === "tool_result") {
            markLastRunningDone();
            const resultStr = chunk.data?.result as string | undefined;

            // Build a result preview
            let resultPreview: string | undefined;
            try {
              if (resultStr) {
                const parsed = JSON.parse(resultStr);
                if (parsed.rows) {
                  resultPreview = `${parsed.row_count || parsed.rows.length} rows returned`;
                } else if (Array.isArray(parsed)) {
                  resultPreview = `${parsed.length} rows returned`;
                } else {
                  resultPreview = resultStr.slice(0, 120);
                }
              }
            } catch {
              resultPreview = resultStr ? resultStr.slice(0, 120) : undefined;
            }

            const stepId = generateStepId();
            const step: AgentStep = {
              id: stepId,
              label: `Results received${chunk.tool_name ? ` from ${chunk.tool_name}` : ""}`,
              status: "done",
              toolName: chunk.tool_name || undefined,
              resultPreview,
              resultData: resultStr || undefined,
              timestamp: chunk.timestamp,
            };
            addAgentStep(step);
            // No running step to track — this step is already "done".
          } else if (chunk.type === "answer") {
            markLastRunningDone();
            const stepId = generateStepId();
            const step: AgentStep = {
              id: stepId,
              label: "Generating answer",
              status: "done",
              detail: chunk.content || undefined,
              timestamp: chunk.timestamp,
            };
            addAgentStep(step);
          } else if (chunk.type === "error") {
            markLastRunningDone();
            const stepId = generateStepId();
            const step: AgentStep = {
              id: stepId,
              label: chunk.content || "Error occurred",
              status: "error",
              timestamp: chunk.timestamp,
            };
            addAgentStep(step);
          }
        },
        onDone: () => {
          // Ensure no step is left in "running" state when the stream ends.
          markLastRunningDone();
          finishStreaming();
        },
        onError: (error) => {
          // Mark any running step as done before reporting the error.
          markLastRunningDone();
          appendChunk({
            type: "error",
            content: error.message || "Connection failed",
            conversation_id: convId!,
            timestamp: Date.now() / 1000,
          });
          finishStreaming();
        },
      });

      abortRef.current = controller;
    },
    [
      isStreaming,
      activeConversationId,
      addUserMessage,
      startAssistantMessage,
      appendChunk,
      finishStreaming,
      addAgentStep,
      updateAgentStep,
      clearAgentSteps,
      newConversation,
    ]
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    finishStreaming();
  }, [finishStreaming]);

  return { sendMessage, stopStreaming, isStreaming };
}
