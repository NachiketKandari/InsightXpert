import { API_BASE_URL } from "./constants";

export interface SSECallbacks {
  onChunk: (data: string) => void;
  onDone: () => void;
  onError: (error: Error) => void;
}

export function createSSEStream(
  message: string,
  conversationId: string | null,
  callbacks: SSECallbacks
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          message,
          conversation_id: conversationId,
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
              callbacks.onDone();
              return;
            }

            callbacks.onChunk(data);
          }
        }
      }

      callbacks.onDone();
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        callbacks.onError(err as Error);
      }
    }
  })();

  return controller;
}
