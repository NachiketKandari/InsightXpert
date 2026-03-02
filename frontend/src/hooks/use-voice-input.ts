"use client";

import { useRef, useState, useCallback } from "react";
import { SSE_BASE_URL } from "@/lib/constants";
import { useAuthStore } from "@/stores/auth-store";

export type VoiceState = "idle" | "requesting" | "listening";

function getWsBaseUrl(): string {
  // Use SSE_BASE_URL (direct to backend) — WebSocket can't go through CDN proxy.
  if (SSE_BASE_URL) {
    const base = SSE_BASE_URL.replace(/^https/, "wss").replace(/^http/, "ws");
    console.debug("[voice] WS base URL (from SSE_BASE_URL):", base);
    return base;
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const base = `${proto}//${window.location.host}`;
  console.debug("[voice] WS base URL (from location):", base);
  return base;
}

/**
 * Streams mic audio to /api/transcribe (backend WS proxy → Deepgram Nova-3).
 *
 * Returns `voiceText` — the full accumulated transcript (committed + interim)
 * — which updates in real-time as the user speaks.  The consumer composites
 * this into the textarea value directly; no callback indirection needed.
 */
export function useVoiceInput() {
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [voiceText, setVoiceText] = useState("");
  const token = useAuthStore((s) => s.token);

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const committedRef = useRef("");
  const interimRef = useRef("");
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const SILENCE_TIMEOUT_MS = 5_000;

  /** Recompute voiceText from committed + interim and push to state. */
  const emit = useCallback(() => {
    const c = committedRef.current;
    const i = interimRef.current;
    const full = i ? (c ? `${c} ${i}` : i) : c;
    setVoiceText(full);
  }, []);

  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    clearSilenceTimer();

    recorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    recorderRef.current = null;
    streamRef.current = null;

    // Absorb any in-flight interim so nothing is lost
    if (interimRef.current) {
      committedRef.current +=
        (committedRef.current ? " " : "") + interimRef.current;
      interimRef.current = "";
    }

    console.debug("[voice] stop — committed:", committedRef.current);

    // Final state push
    setVoiceText(committedRef.current);
    committedRef.current = "";

    wsRef.current?.close();
    wsRef.current = null;
    setVoiceState("idle");
  }, [clearSilenceTimer]);

  const start = useCallback(async () => {
    // Reset from any previous session
    committedRef.current = "";
    interimRef.current = "";
    setVoiceText("");
    setVoiceError(null);
    setVoiceState("requesting");

    console.debug("[voice] start — requesting mic");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setVoiceError("Microphone access denied");
      setVoiceState("idle");
      return;
    }

    streamRef.current = stream;

    // Build WS URL with auth token (cookies may not reach Cloud Run directly)
    const wsUrl = new URL(`${getWsBaseUrl()}/api/transcribe`);
    if (token) wsUrl.searchParams.set("token", token);
    console.debug("[voice] WS URL:", wsUrl.toString());

    const ws = new WebSocket(wsUrl.toString());
    wsRef.current = ws;
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      console.debug("[voice] WS open");
      setVoiceState("listening");

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType });
      recorderRef.current = recorder;
      console.debug("[voice] MediaRecorder started, mimeType:", mimeType);

      recorder.addEventListener("dataavailable", (e) => {
        if (e.data.size > 0 && ws.readyState === WebSocket.OPEN) {
          ws.send(e.data);
        }
      });
      recorder.start(250);

      // Start silence timer — auto-stop if no speech within timeout
      silenceTimerRef.current = setTimeout(() => stop(), SILENCE_TIMEOUT_MS);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data as string);

        if (data.error) {
          setVoiceError(data.error as string);
          stop();
          return;
        }

        const transcript =
          (data?.channel?.alternatives?.[0]?.transcript as string) ?? "";

        console.debug(
          "[voice] DG message — is_final:", data.is_final,
          "speech_final:", data.speech_final,
          "transcript:", transcript.slice(0, 60),
        );

        if (data.is_final) {
          if (transcript) {
            committedRef.current +=
              (committedRef.current ? " " : "") + transcript;
          }
          interimRef.current = "";
          emit();

          // Reset silence timer — speech was detected
          if (transcript) {
            clearSilenceTimer();
            silenceTimerRef.current = setTimeout(() => stop(), SILENCE_TIMEOUT_MS);
          }

          if (data.speech_final) {
            stop();
          }
        } else if (transcript) {
          interimRef.current = transcript;
          emit();

          // Any interim speech resets the silence clock
          clearSilenceTimer();
          silenceTimerRef.current = setTimeout(() => stop(), SILENCE_TIMEOUT_MS);
        }
      } catch {
        // ignore keepalive / non-JSON frames
      }
    };

    ws.onerror = (ev) => {
      console.debug("[voice] WS error:", ev);
      setVoiceError("Voice connection failed");
      stop();
    };

    ws.onclose = (event) => {
      console.debug("[voice] WS close — code:", event.code, "reason:", event.reason);
      clearSilenceTimer();
      recorderRef.current?.stop();
      streamRef.current?.getTracks().forEach((t) => t.stop());
      recorderRef.current = null;
      streamRef.current = null;
      wsRef.current = null;
      setVoiceState("idle");

      if (event.code === 4001) {
        setVoiceError("Not authenticated — please log in again");
      } else if (event.code === 4002) {
        setVoiceError("Speech-to-text is not configured");
      }
    };
  }, [stop, emit, clearSilenceTimer, token]);

  const toggleVoice = useCallback(() => {
    if (voiceState === "idle") start();
    else stop();
  }, [voiceState, start, stop]);

  return { voiceState, voiceError, voiceText, toggleVoice };
}
