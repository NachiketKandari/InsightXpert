import { SSE_BASE_URL } from "./constants";

export interface SSECallbacks {
  onChunk: (data: string) => void;
  onDone: () => void;
  onError: (error: Error) => void;
}

export type AgentMode = "basic" | "agentic" | "deep";

export interface SSEOptions {
  skipClarification?: boolean;
}

export function createSSEStream(
  message: string,
  conversationId: string | null,
  callbacks: SSECallbacks,
  agentMode: AgentMode = "basic",
  options: SSEOptions = {},
  token?: string | null,
): AbortController {
  const controller = new AbortController();

  (async () => {
    const chunkQueue: string[] = [];
    let draining = false;
    let streamDone = false;

    function drainQueue() {
      while (chunkQueue.length > 0) {
        const data = chunkQueue.shift()!;
        callbacks.onChunk(data);
      }
      draining = false;
      if (streamDone) {
        callbacks.onDone();
      }
    }

    function enqueue(data: string) {
      chunkQueue.push(data);
      if (!draining) {
        draining = true;
        // Defer to next tick so all chunks from the same reader.read()
        // batch are queued before we start delivering them one by one.
        queueMicrotask(drainQueue);
      }
    }

    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const response = await fetch(`${SSE_BASE_URL}/api/chat`, {
        method: "POST",
        headers,
        credentials: "include",
        body: JSON.stringify({
          message,
          conversation_id: conversationId,
          agent_mode: agentMode,
          ...(options.skipClarification ? { skip_clarification: true } : {}),
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || trimmed.startsWith(":")) continue;

          if (trimmed.startsWith("data: ") || trimmed.startsWith("data:")) {
            const data = trimmed.startsWith("data: ")
              ? trimmed.slice(6)
              : trimmed.slice(5);

            if (data === "[DONE]") {
              streamDone = true;
              if (!draining) {
                callbacks.onDone();
              }
              return;
            }

            enqueue(data);
          }
        }
      }

      streamDone = true;
      if (!draining) {
        callbacks.onDone();
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        callbacks.onError(err as Error);
      }
    }
  })();

  return controller;
}
