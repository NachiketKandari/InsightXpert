"use client";

import { useState, useMemo, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  XCircle,
  Clock,
  Database,
  Brain,
  ExternalLink,
} from "lucide-react";
import { TraceModal } from "./trace-modal";
import type { OrchestratorPlan, AgentTrace, EnrichmentTrace } from "@/types/chat";

interface ThinkingTraceProps {
  plan: OrchestratorPlan;
  traces: AgentTrace[];
  enrichmentTraces?: EnrichmentTrace[];
}

const agentLabels: Record<string, string> = {
  sql_analyst: "SQL Analyst",
  quant_analyst: "Quant Analyst",
};

const agentColors: Record<string, string> = {
  sql_analyst: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  quant_analyst: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
};

const categoryLabels: Record<string, string> = {
  comparative_context: "Comparative",
  temporal_trend: "Temporal",
  root_cause: "Root Cause",
  segmentation: "Segmentation",
};

const categoryColors: Record<string, string> = {
  comparative_context: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  temporal_trend: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-300",
  root_cause: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
  segmentation: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
};

export function ThinkingTrace({ plan, traces, enrichmentTraces }: ThinkingTraceProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTrace, setActiveTrace] = useState<EnrichmentTrace | null>(null);

  const totalTimeMs = traces.reduce((sum, t) => sum + (t.duration_ms || 0), 0);
  const successCount = traces.filter((t) => t.success).length;
  const totalCount = plan.tasks.length;

  // Map task_id → enrichment trace by source_index order
  const traceByTaskId = useMemo(() => {
    const m = new Map<string, EnrichmentTrace>();
    if (!enrichmentTraces?.length) return m;
    plan.tasks.forEach((task, i) => {
      const et = enrichmentTraces.find((t) => t.source_index === i + 1);
      if (et) m.set(task.id, et);
    });
    return m;
  }, [plan.tasks, enrichmentTraces]);

  const handleViewDetails = useCallback(
    (taskId: string) => {
      const et = traceByTaskId.get(taskId);
      if (et) setActiveTrace(et);
    },
    [traceByTaskId],
  );

  return (
    <>
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-left text-sm transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-800/50 dark:hover:bg-zinc-800">
          {isOpen ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-zinc-400" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-zinc-400" />
          )}
          <Brain className="h-4 w-4 shrink-0 text-zinc-500" />
          <span className="font-medium text-zinc-700 dark:text-zinc-300">
            Thinking process
          </span>
          <Badge variant="secondary" className="ml-1 text-xs">
            {totalCount} task{totalCount !== 1 ? "s" : ""}
          </Badge>
          {successCount < totalCount && (
            <Badge variant="destructive" className="text-xs">
              {totalCount - successCount} failed
            </Badge>
          )}
          {totalTimeMs > 0 && (
            <span className="ml-auto flex items-center gap-1 text-xs text-zinc-400">
              <Clock className="h-3 w-3" />
              {(totalTimeMs / 1000).toFixed(1)}s
            </span>
          )}
        </CollapsibleTrigger>

        <CollapsibleContent>
          <div className="mt-2 space-y-2 rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
            {/* Reasoning */}
            {plan.reasoning && (
              <div className="text-xs text-zinc-500 dark:text-zinc-400 italic mb-3">
                {plan.reasoning}
              </div>
            )}

            {/* Task cards */}
            {plan.tasks.map((task) => {
              const trace = traces.find((t) => t.task_id === task.id);
              const hasEnrichment = traceByTaskId.has(task.id);
              return (
                <TaskCard
                  key={task.id}
                  task={task}
                  trace={trace}
                  onViewDetails={hasEnrichment ? () => handleViewDetails(task.id) : undefined}
                />
              );
            })}
          </div>
        </CollapsibleContent>
      </Collapsible>

      <TraceModal
        trace={activeTrace}
        open={activeTrace != null}
        onOpenChange={(open) => {
          if (!open) setActiveTrace(null);
        }}
      />
    </>
  );
}

function TaskCard({
  task,
  trace,
  onViewDetails,
}: {
  task: { id: string; agent: string; category?: string; task: string; depends_on: string[] };
  trace?: AgentTrace;
  onViewDetails?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const success = trace?.success ?? false;
  const agentLabel = agentLabels[task.agent] || task.agent;
  const colorClass = agentColors[task.agent] || "bg-zinc-100 text-zinc-700";

  return (
    <div className="rounded-md border border-zinc-100 dark:border-zinc-800">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
      >
        {trace ? (
          success ? (
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
          ) : (
            <XCircle className="h-4 w-4 shrink-0 text-red-500" />
          )
        ) : (
          <Clock className="h-4 w-4 shrink-0 text-zinc-400" />
        )}

        <span className="font-mono text-xs font-bold text-zinc-400">
          [{task.id}]
        </span>

        <Badge className={`text-xs ${colorClass}`}>
          {agentLabel}
        </Badge>

        {task.category && categoryLabels[task.category] && (
          <Badge className={`text-xs ${categoryColors[task.category] || "bg-zinc-100 text-zinc-700"}`}>
            {categoryLabels[task.category]}
          </Badge>
        )}

        <span className="flex-1 truncate text-zinc-600 dark:text-zinc-300">
          {task.task}
        </span>

        {task.depends_on.length > 0 && (
          <span className="text-xs text-zinc-400">
            depends: {task.depends_on.join(", ")}
          </span>
        )}

        {trace?.duration_ms && (
          <span className="text-xs text-zinc-400">
            {(trace.duration_ms / 1000).toFixed(1)}s
          </span>
        )}

        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-zinc-400" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0 text-zinc-400" />
        )}
      </button>

      {expanded && trace && (
        <div className="border-t border-zinc-100 px-3 py-2 text-xs dark:border-zinc-800">
          {trace.final_sql && (
            <div className="mb-2">
              <div className="flex items-center gap-1 font-medium text-zinc-500 mb-1">
                <Database className="h-3 w-3" />
                SQL
              </div>
              <pre className="overflow-x-auto rounded bg-zinc-50 p-2 text-xs dark:bg-zinc-800">
                {trace.final_sql}
              </pre>
            </div>
          )}

          {trace.final_answer && (
            <div className="mb-2">
              <div className="flex items-center gap-1 font-medium text-zinc-500 mb-1">
                <Brain className="h-3 w-3" />
                Answer
              </div>
              <div className="prose-sm max-w-none text-zinc-600 dark:text-zinc-300">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {trace.final_answer.length > 800
                    ? trace.final_answer.slice(0, 800) + "\n\n..."
                    : trace.final_answer}
                </ReactMarkdown>
              </div>
            </div>
          )}

          {trace.error && (
            <div className="text-red-500 dark:text-red-400 mb-2">
              Error: {trace.error}
            </div>
          )}

          {onViewDetails && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onViewDetails();
              }}
              className="flex items-center gap-1.5 text-xs text-primary hover:text-primary/80 transition-colors mt-1"
            >
              <ExternalLink className="h-3 w-3" />
              View full trace
            </button>
          )}
        </div>
      )}
    </div>
  );
}
