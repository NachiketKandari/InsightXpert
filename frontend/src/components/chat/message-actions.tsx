"use client";

import { useState } from "react";
import { Check, Copy, ThumbsUp, ThumbsDown, RotateCcw, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface MessageActionsProps {
  role: "user" | "assistant";
  content: string;
  isLastAssistant?: boolean;
  onRetry?: () => void;
  onFeedback?: (type: "up" | "down", comment?: string) => void;
}

export function MessageActions({
  role,
  content,
  isLastAssistant,
  onRetry,
  onFeedback,
}: MessageActionsProps) {
  const [copied, setCopied] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState<"up" | "down" | null>(null);
  const [showFeedbackInput, setShowFeedbackInput] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleThumbsUp = () => {
    setFeedbackGiven("up");
    setShowFeedbackInput(false);
    onFeedback?.("up");
  };

  const handleThumbsDown = () => {
    setFeedbackGiven("down");
    setShowFeedbackInput(true);
  };

  const handleSubmitFeedback = () => {
    onFeedback?.("down", feedbackText);
    setShowFeedbackInput(false);
    setFeedbackText("");
  };

  if (!content) return null;

  return (
    <div className="flex flex-col gap-1.5">
      <div
        className={cn(
          "flex items-center gap-0.5 transition-opacity",
          "opacity-0 group-hover/message:opacity-100",
          "max-sm:opacity-100",
          role === "user" ? "justify-end" : "justify-start"
        )}
      >
        {/* Copy */}
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={handleCopy}
          className="text-muted-foreground hover:text-foreground"
          aria-label={role === "user" ? "Copy prompt" : "Copy response"}
        >
          {copied ? (
            <Check className="size-3 text-emerald-400" />
          ) : (
            <Copy className="size-3" />
          )}
        </Button>

        {/* Assistant-only actions */}
        {role === "assistant" && (
          <>
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={handleThumbsUp}
              className={cn(
                "text-muted-foreground hover:text-foreground",
                feedbackGiven === "up" && "text-emerald-400 hover:text-emerald-400"
              )}
              aria-label="Good response"
            >
              <ThumbsUp className="size-3" />
            </Button>

            <Button
              variant="ghost"
              size="icon-xs"
              onClick={handleThumbsDown}
              className={cn(
                "text-muted-foreground hover:text-foreground",
                feedbackGiven === "down" && "text-red-400 hover:text-red-400"
              )}
              aria-label="Bad response"
            >
              <ThumbsDown className="size-3" />
            </Button>

            {isLastAssistant && onRetry && (
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={onRetry}
                className="text-muted-foreground hover:text-foreground"
                aria-label="Retry"
              >
                <RotateCcw className="size-3" />
              </Button>
            )}
          </>
        )}
      </div>

      {/* Feedback input */}
      {showFeedbackInput && (
        <div className="flex items-center gap-2 rounded-lg border border-border bg-card/50 px-3 py-1.5">
          <input
            type="text"
            value={feedbackText}
            onChange={(e) => setFeedbackText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSubmitFeedback();
            }}
            placeholder="What went wrong? (optional)"
            className="flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
            autoFocus
          />
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={handleSubmitFeedback}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Submit feedback"
          >
            <Send className="size-3" />
          </Button>
        </div>
      )}
    </div>
  );
}
