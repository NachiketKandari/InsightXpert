"use client";

import { SearchCheck, X } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/stores/chat-store";
import type { InvestigationSuggestion } from "@/types/chat";

const CATEGORY_COLORS: Record<string, string> = {
  comparative_context: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  temporal_trend: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
  root_cause: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  segmentation: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
};

const CATEGORY_LABELS: Record<string, string> = {
  comparative_context: "Comparative",
  temporal_trend: "Temporal",
  root_cause: "Root Cause",
  segmentation: "Segmentation",
};

interface InvestigationSuggestionChunkProps {
  content: string;
  data?: Record<string, unknown> | null;
}

export function InvestigationSuggestionChunk({
  content,
  data,
}: InvestigationSuggestionChunkProps) {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const pendingInvestigation = useChatStore((s) => s.pendingInvestigation);

  const suggestion = data as unknown as InvestigationSuggestion | undefined;
  const tasks = suggestion?.tasks ?? [];

  const showButtons = pendingInvestigation && !isStreaming;

  const handleInvestigate = () => {
    useChatStore.getState().setPendingInput("__INVESTIGATE__");
  };

  const handleSkip = () => {
    useChatStore.getState().setPendingInvestigation(null);
  };

  return (
    <Card className="border-l-4 border-l-indigo-500 border-indigo-200/50 bg-indigo-50/50 dark:bg-indigo-950/20 dark:border-indigo-800/50">
      <CardContent className="py-3">
        <div className="flex items-start gap-3">
          <SearchCheck className="h-4 w-4 text-indigo-600 dark:text-indigo-400 shrink-0 mt-0.5" />
          <div className="flex-1 space-y-2">
            <p className="text-sm font-medium text-indigo-900 dark:text-indigo-200">
              More data available &mdash; Investigate?
            </p>
            <p className="text-sm text-indigo-800/80 dark:text-indigo-300/80">
              {content}
            </p>
            {tasks.length > 0 && (
              <div className="space-y-1.5 mt-2">
                {tasks.map((task) => (
                  <div key={task.id} className="flex items-start gap-2">
                    <Badge
                      variant="secondary"
                      className={`text-[10px] px-1.5 py-0 shrink-0 mt-0.5 ${
                        CATEGORY_COLORS[task.category ?? ""] ?? "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"
                      }`}
                    >
                      {CATEGORY_LABELS[task.category ?? ""] ?? task.category ?? "Analysis"}
                    </Badge>
                    <span className="text-xs text-indigo-700 dark:text-indigo-300">
                      {task.task}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {showButtons && (
              <div className="flex items-center gap-2 mt-3">
                <Button
                  size="sm"
                  className="h-7 text-xs bg-indigo-600 hover:bg-indigo-700 text-white"
                  onClick={handleInvestigate}
                >
                  <SearchCheck className="h-3 w-3 mr-1" />
                  Investigate
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-200"
                  onClick={handleSkip}
                >
                  <X className="h-3 w-3 mr-1" />
                  Skip
                </Button>
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
