"use client";

import { useEffect } from "react";
import {
  Plus,
  Paperclip,
  TerminalSquare,
  Sparkles,
  Zap,
  Brain,
  Check,
  ChevronDown,
  ArrowUp,
  Square,
  Network,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import { useSettingsStore } from "@/stores/settings-store";
import { useChatStore } from "@/stores/chat-store";
import { useClientConfig } from "@/hooks/use-client-config";
import { PROVIDER_LABELS, formatModelName } from "@/lib/model-utils";

interface InputToolbarProps {
  onSend: () => void;
  onStop: () => void;
  isStreaming: boolean;
  canSend: boolean;
}

export function InputToolbar({
  onSend,
  onStop,
  isStreaming,
  canSend,
}: InputToolbarProps) {
  const { isFeatureEnabled } = useClientConfig();
  const showModelSwitching = isFeatureEnabled("model_switching");
  const showSqlExecutor = isFeatureEnabled("sql_executor");

  const agentMode = useSettingsStore((s) => s.agentMode);
  const setAgentMode = useSettingsStore((s) => s.setAgentMode);

  const setSqlExecutorOpen = useChatStore((s) => s.setSqlExecutorOpen);
  const currentAgentPhase = useChatStore((s) => s.currentAgentPhase);

  const currentProvider = useSettingsStore((s) => s.currentProvider);
  const currentModel = useSettingsStore((s) => s.currentModel);
  const providers = useSettingsStore((s) => s.providers);
  const loading = useSettingsStore((s) => s.loading);
  const fetchConfig = useSettingsStore((s) => s.fetchConfig);
  const switchModel = useSettingsStore((s) => s.switchModel);

  useEffect(() => {
    if (showModelSwitching) fetchConfig();
  }, [showModelSwitching, fetchConfig]);

  const providerLabel = PROVIDER_LABELS[currentProvider] ?? currentProvider;
  const displayModel = formatModelName(currentModel, currentProvider);

  const handleModelSelect = (provider: string, model: string) => {
    if (provider === currentProvider && model === currentModel) return;
    switchModel(provider, model);
  };

  // Resolve what the agent mode tag should display
  const showPhase = isStreaming && !!currentAgentPhase;
  const activeKey = showPhase ? currentAgentPhase! : agentMode;

  const modeConfig = {
    basic: {
      label: "SQL Only",
      icon: Sparkles,
      color: "text-amber-500",
      bg: "bg-amber-500/10",
      border: "border-amber-500/30",
    },
    agentic: {
      label: "Agentic",
      icon: Zap,
      color: "text-emerald-500",
      bg: "bg-emerald-500/10",
      border: "border-emerald-500/30",
    },
    deep: {
      label: "Deep Think",
      icon: Brain,
      color: "text-violet-500",
      bg: "bg-violet-500/10",
      border: "border-violet-500/30",
    },
    deep_think: {
      label: "Deep Thinking",
      icon: Brain,
      color: "text-violet-500",
      bg: "bg-violet-500/10",
      border: "border-violet-500/30",
    },
    analyst: {
      label: "Analyzing",
      icon: Sparkles,
      color: "text-amber-500",
      bg: "bg-amber-500/10",
      border: "border-amber-500/30",
    },
    orchestrator: {
      label: "Orchestrating",
      icon: Network,
      color: "text-cyan-500",
      bg: "bg-cyan-500/10",
      border: "border-cyan-500/30",
    },
    insight: {
      label: "Insight",
      icon: Zap,
      color: "text-emerald-500",
      bg: "bg-emerald-500/10",
      border: "border-emerald-500/30",
    },
  } as const;

  const active = modeConfig[activeKey as keyof typeof modeConfig] ?? modeConfig.basic;
  const ActiveIcon = active.icon;

  return (
    <div className="flex items-center justify-between pt-1">
      {/* Left: + menu and agent mode tag */}
      <div className="flex items-center gap-1">
        {/* + menu */}
        <DropdownMenu>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger asChild>
                <button
                  className="flex items-center justify-center size-7 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors outline-none"
                  aria-label="More options"
                >
                  <Plus className="size-4" />
                </button>
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <TooltipContent side="top">Attach, tools & agents</TooltipContent>
          </Tooltip>
          <DropdownMenuContent side="top" align="start" className="min-w-[200px]">
            <DropdownMenuItem disabled>
              <Paperclip className="size-4" />
              Upload CSV
              <span className="ml-auto text-[10px] text-muted-foreground/60">Soon</span>
            </DropdownMenuItem>

            {showSqlExecutor && (
              <DropdownMenuItem onSelect={() => setSqlExecutorOpen(true)}>
                <TerminalSquare className="size-4" />
                SQL Executor
              </DropdownMenuItem>
            )}

            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              Analysis Mode
            </DropdownMenuLabel>
            <DropdownMenuItem onSelect={() => setAgentMode("basic")}>
              <Sparkles className="size-4" />
              SQL Only
              {agentMode === "basic" && <Check className="size-3.5 ml-auto text-emerald-500" />}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setAgentMode("agentic")}>
              <Zap className="size-4" />
              Agentic
              {agentMode === "agentic" && <Check className="size-3.5 ml-auto text-emerald-500" />}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setAgentMode("deep")}>
              <Brain className="size-4" />
              Deep Think
              {agentMode === "deep" && <Check className="size-3.5 ml-auto text-emerald-500" />}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Agent mode selector tag */}
        {showPhase ? (
          /* During streaming: show active phase as a static pill (no dropdown) */
          <div
            className={`flex items-center gap-1.5 rounded-lg px-2.5 py-0.5 text-xs font-medium border transition-colors ${active.bg} ${active.border} ${active.color}`}
          >
            <ActiveIcon className="size-3 animate-pulse" />
            <span>{active.label}</span>
          </div>
        ) : (
          /* When idle: clickable dropdown selector */
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className={`flex items-center gap-1.5 rounded-lg px-2.5 py-0.5 text-xs font-medium border transition-colors outline-none hover:brightness-110 ${active.bg} ${active.border} ${active.color}`}
              >
                <ActiveIcon className="size-3" />
                <span>{active.label}</span>
                <ChevronDown className="size-3 opacity-60" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="start" className="min-w-[170px]">
              <DropdownMenuLabel className="text-xs text-muted-foreground">
                Agent Mode
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setAgentMode("basic")}>
                <Sparkles className="size-4 text-amber-500" />
                SQL Only
                {agentMode === "basic" && <Check className="size-3.5 ml-auto text-emerald-500" />}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setAgentMode("agentic")}>
                <Zap className="size-4 text-emerald-500" />
                Agentic
                {agentMode === "agentic" && <Check className="size-3.5 ml-auto text-emerald-500" />}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setAgentMode("deep")}>
                <Brain className="size-4 text-violet-500" />
                Deep Think
                {agentMode === "deep" && <Check className="size-3.5 ml-auto text-emerald-500" />}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      {/* Right: Model selector + Send/Stop */}
      <div className="flex items-center gap-1">
        {showModelSwitching && (
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors outline-none disabled:opacity-50 max-w-[160px] md:max-w-none"
                    disabled={loading}
                  >
                    <span className="truncate">
                      {providerLabel} {displayModel}
                    </span>
                    <ChevronDown className="size-3 opacity-50 shrink-0" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  side="top"
                  align="end"
                  className="min-w-[200px]"
                >
                  {providers.map((p) => (
                    <DropdownMenuSub key={p.provider}>
                      <DropdownMenuSubTrigger>
                        {PROVIDER_LABELS[p.provider] ?? p.provider}
                      </DropdownMenuSubTrigger>
                      <DropdownMenuSubContent>
                        <DropdownMenuRadioGroup
                          value={
                            p.provider === currentProvider ? currentModel : ""
                          }
                          onValueChange={(model) =>
                            handleModelSelect(p.provider, model)
                          }
                        >
                          {p.models.map((model) => (
                            <DropdownMenuRadioItem key={model} value={model}>
                              {formatModelName(model, p.provider)}
                            </DropdownMenuRadioItem>
                          ))}
                        </DropdownMenuRadioGroup>
                      </DropdownMenuSubContent>
                    </DropdownMenuSub>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </TooltipTrigger>
            <TooltipContent side="top">Switch model</TooltipContent>
          </Tooltip>
        )}

        {isStreaming ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon"
                variant="ghost"
                onClick={onStop}
                className="h-8 w-8 shrink-0 rounded-lg text-destructive hover:bg-destructive/10"
              >
                <Square className="h-4 w-4 fill-current" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top">Stop generating</TooltipContent>
          </Tooltip>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon"
                onClick={onSend}
                disabled={!canSend}
                className="h-8 w-8 shrink-0 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-30"
              >
                <ArrowUp className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top">Send message</TooltipContent>
          </Tooltip>
        )}
      </div>
    </div>
  );
}
