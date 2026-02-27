"use client";

import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import type { FeatureToggles } from "@/types/admin";
import {
  TerminalSquare,
  RefreshCw,
  Database,
  BarChart3,
  Download,
  PanelRight,
  HelpCircle,
  Sparkles,
} from "lucide-react";

const FEATURE_DEFS: {
  key: keyof FeatureToggles;
  label: string;
  description: string;
  icon: React.ElementType;
}[] = [
  {
    key: "sql_executor",
    label: "SQL Executor",
    description: "Allow users to run SQL queries directly",
    icon: TerminalSquare,
  },
  {
    key: "model_switching",
    label: "Model Switching",
    description: "Allow users to switch LLM providers and models",
    icon: RefreshCw,
  },
  {
    key: "rag_training",
    label: "RAG Training",
    description: "Allow users to add training data to the knowledge base",
    icon: Database,
  },
  {
    key: "chart_rendering",
    label: "Chart Rendering",
    description: "Show auto-generated charts for query results",
    icon: BarChart3,
  },
  {
    key: "conversation_export",
    label: "Conversation Export",
    description: "Allow users to export conversations",
    icon: Download,
  },
  {
    key: "agent_process_sidebar",
    label: "Agent Process Sidebar",
    description: "Show the agent process timeline sidebar",
    icon: PanelRight,
  },
  {
    key: "clarification_enabled",
    label: "Question Clarification",
    description: "Ask for clarification before answering ambiguous questions (adds latency)",
    icon: HelpCircle,
  },
  {
    key: "stats_context_injection",
    label: "Pre-Computed Stats Context",
    description: "Inject pre-configured dataset statistics directly into the LLM context, enabling faster answers without SQL for common aggregate questions",
    icon: Sparkles,
  },
];

interface FeatureTogglesEditorProps {
  features: FeatureToggles;
  onChange: (features: FeatureToggles) => void;
}

export function FeatureTogglesEditor({
  features,
  onChange,
}: FeatureTogglesEditorProps) {
  const toggle = (key: keyof FeatureToggles) => {
    onChange({ ...features, [key]: !features[key] });
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-muted-foreground">
        Feature Toggles
      </h3>
      <div className="grid gap-4 sm:grid-cols-2">
        {FEATURE_DEFS.map(({ key, label, description, icon: Icon }) => (
          <div
            key={key}
            className="flex items-start gap-3 rounded-lg border border-border p-4"
          >
            <Icon className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
            <div className="flex-1 space-y-1">
              <Label
                htmlFor={key}
                className="text-sm font-medium leading-none cursor-pointer"
              >
                {label}
              </Label>
              <p className="text-xs text-muted-foreground">{description}</p>
            </div>
            <Switch
              id={key}
              checked={features[key]}
              onCheckedChange={() => toggle(key)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
