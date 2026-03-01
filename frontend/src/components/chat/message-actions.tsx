"use client";

import { useState } from "react";
import { Check, Copy, ThumbsUp, ThumbsDown, RotateCcw, Send, Lightbulb, Download, FileText, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import { cn, relativeTime, formatDate } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface MessageActionsProps {
  role: "user" | "assistant";
  content: string;
  timestamp?: number;
  isLastAssistant?: boolean;
  onRetry?: () => void;
  onResend?: (content: string) => void;
  onFeedback?: (type: "up" | "down", comment?: string) => void;
  onMarkInsight?: (note?: string) => void;
  onDownloadMessage?: () => void;
  onDownloadConversation?: () => void;
}

export function MessageActions({
  role,
  content,
  timestamp,
  isLastAssistant,
  onRetry,
  onResend,
  onFeedback,
  onMarkInsight,
  onDownloadMessage,
  onDownloadConversation,
}: MessageActionsProps) {
  const [copied, setCopied] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState<"up" | "down" | null>(null);
  const [showFeedbackInput, setShowFeedbackInput] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");
  const [insightMarked, setInsightMarked] = useState(false);
  const [showInsightInput, setShowInsightInput] = useState(false);
  const [insightNote, setInsightNote] = useState("");

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

  const handleInsightClick = () => {
    if (insightMarked) return;
    setShowInsightInput(true);
  };

  const handleSubmitInsight = () => {
    setInsightMarked(true);
    setShowInsightInput(false);
    onMarkInsight?.(insightNote || undefined);
    setInsightNote("");
  };

  if (!content) return null;

  return (
    <div className="flex flex-col gap-1.5">
      <div
        className={cn(
          "flex items-center gap-0.5",
          role === "user" ? "justify-end" : "justify-start"
        )}
      >
        {/* Copy */}
        <Tooltip>
          <TooltipTrigger asChild>
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
          </TooltipTrigger>
          <TooltipContent side="bottom">
            {copied ? "Copied!" : "Copy"}
          </TooltipContent>
        </Tooltip>

        {/* User-only actions: Resend + Timestamp */}
        {role === "user" && onResend && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={() => onResend(content)}
                className="text-muted-foreground hover:text-foreground"
                aria-label="Resend"
              >
                <RotateCcw className="size-3" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Resend</TooltipContent>
          </Tooltip>
        )}

        {role === "user" && timestamp && (
          <span className="text-[10px] text-muted-foreground/60 select-none ml-0.5">
            {(() => {
              const startOfToday = new Date();
              startOfToday.setHours(0, 0, 0, 0);
              return timestamp >= startOfToday.getTime()
                ? relativeTime(timestamp)
                : formatDate(timestamp);
            })()}
          </span>
        )}

        {/* Assistant-only actions */}
        {role === "assistant" && (
          <>
            <Tooltip>
              <TooltipTrigger asChild>
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
              </TooltipTrigger>
              <TooltipContent side="bottom">Good response</TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
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
              </TooltipTrigger>
              <TooltipContent side="bottom">Bad response</TooltipContent>
            </Tooltip>

            {onMarkInsight && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    onClick={handleInsightClick}
                    className={cn(
                      "text-muted-foreground hover:text-foreground",
                      insightMarked && "text-amber-400 hover:text-amber-400"
                    )}
                    disabled={insightMarked}
                    aria-label="Mark as insight"
                  >
                    <Lightbulb className={cn("size-3", insightMarked && "fill-current")} />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  {insightMarked ? "Saved as insight" : "Mark as insight"}
                </TooltipContent>
              </Tooltip>
            )}

            {(onDownloadMessage || onDownloadConversation) && (
              <DropdownMenu>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        className="text-muted-foreground hover:text-foreground"
                        aria-label="Download report"
                      >
                        <Download className="size-3" />
                      </Button>
                    </DropdownMenuTrigger>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">Download</TooltipContent>
                </Tooltip>
                <DropdownMenuContent align="start" className="min-w-[180px]">
                  {onDownloadMessage && (
                    <DropdownMenuItem onClick={onDownloadMessage}>
                      <FileText className="size-3.5 mr-2" />
                      Message Report
                    </DropdownMenuItem>
                  )}
                  {onDownloadConversation && (
                    <DropdownMenuItem onClick={onDownloadConversation}>
                      <MessageSquare className="size-3.5 mr-2" />
                      Conversation Report
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}

            {isLastAssistant && onRetry && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    onClick={onRetry}
                    className="text-muted-foreground hover:text-foreground"
                    aria-label="Retry"
                  >
                    <RotateCcw className="size-3" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom">Retry</TooltipContent>
              </Tooltip>
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
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={handleSubmitFeedback}
                className="text-muted-foreground hover:text-foreground"
                aria-label="Submit feedback"
              >
                <Send className="size-3" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top">Submit feedback</TooltipContent>
          </Tooltip>
        </div>
      )}

      {/* Insight note input */}
      {showInsightInput && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-1.5">
          <Lightbulb className="size-3 text-amber-500 shrink-0" />
          <input
            type="text"
            value={insightNote}
            onChange={(e) => setInsightNote(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSubmitInsight();
            }}
            placeholder="Why is this an insight? (optional)"
            className="flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
            autoFocus
          />
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={handleSubmitInsight}
                className="text-amber-500 hover:text-amber-400"
                aria-label="Save insight"
              >
                <Send className="size-3" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top">Save insight</TooltipContent>
          </Tooltip>
        </div>
      )}
    </div>
  );
}
