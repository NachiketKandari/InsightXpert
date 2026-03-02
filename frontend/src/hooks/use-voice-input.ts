"use client";

import { useRef, useState, useCallback } from "react";
import { API_BASE_URL } from "@/lib/constants";

export type VoiceState = "idle" | "requesting" | "listening";

function getWsBaseUrl(): string {
  if (API_BASE_URL) {
    return API_BASE_URL.replace(/^https/, "wss").replace(/^http/, "ws");
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
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

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setVoiceError("Microphone access denied");
      setVoiceState("idle");
      return;
    }

    streamRef.current = stream;
    const ws = new WebSocket(`${getWsBaseUrl()}/api/transcribe`);
    wsRef.current = ws;
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      setVoiceState("listening");

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType });
      recorderRef.current = recorder;

      recorder.addEventListener("dataavailable", (e) => {
        if (e.data.size > 0 && ws.readyState === WebSocket.OPEN) {
          ws.send(e.data);
        }
      });
      recorder.start(250);

      // Start silence timer — auto-stop if no speech within 3s
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

    ws.onerror = () => {
      setVoiceError("Voice connection failed");
      stop();
    };

    ws.onclose = (event) => {
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
  }, [stop, emit, clearSilenceTimer]);

  const toggleVoice = useCallback(() => {
    if (voiceState === "idle") start();
    else stop();
  }, [voiceState, start, stop]);

  return { voiceState, voiceError, voiceText, toggleVoice };
}
