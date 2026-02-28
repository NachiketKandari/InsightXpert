"use client";

import { useState } from "react";
import { Plus, Sparkles, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiCall } from "@/lib/api";
import { ConditionRow } from "./condition-row";
import type { TriggerCondition } from "@/types/automation";
import type { ResultShape } from "@/lib/automation-utils";

interface TriggerConditionBuilderProps {
  conditions: TriggerCondition[];
  onChange: (conditions: TriggerCondition[]) => void;
  columns: string[];
  resultShape: ResultShape;
}

export function TriggerConditionBuilder({
  conditions,
  onChange,
  columns,
  resultShape,
}: TriggerConditionBuilderProps) {
  const [showNlInput, setShowNlInput] = useState(false);
  const [nlText, setNlText] = useState("");
  const [isCompiling, setIsCompiling] = useState(false);
  const [compiledPreview, setCompiledPreview] = useState<TriggerCondition | null>(null);
  const [compileError, setCompileError] = useState<string | null>(null);

  const addCondition = () => {
    const defaultType = resultShape === "scalar" ? "threshold" : "row_count";
    onChange([
      ...conditions,
      { type: defaultType, column: null, operator: "gt", value: null, change_percent: null, scope: null },
    ]);
  };

  const updateCondition = (index: number, updated: TriggerCondition) => {
    const next = [...conditions];
    next[index] = updated;
    onChange(next);
  };

  const removeCondition = (index: number) => {
    onChange(conditions.filter((_, i) => i !== index));
  };

  const handleCompile = async () => {
    if (!nlText.trim()) return;
    setIsCompiling(true);
    setCompileError(null);
    setCompiledPreview(null);

    const result = await apiCall<TriggerCondition>("/api/automations/compile-trigger", {
      method: "POST",
      body: JSON.stringify({
        nl_text: nlText.trim(),
        available_columns: columns.length > 0 ? columns : null,
      }),
    });

    setIsCompiling(false);
    if (result) {
      setCompiledPreview(result);
    } else {
      setCompileError("Could not compile trigger. Try rephrasing.");
    }
  };

  const handleAcceptCompiled = () => {
    if (!compiledPreview) return;
    onChange([...conditions, compiledPreview]);
    // Reset NL input state
    setShowNlInput(false);
    setNlText("");
    setCompiledPreview(null);
    setCompileError(null);
  };

  const handleCancelNl = () => {
    setShowNlInput(false);
    setNlText("");
    setCompiledPreview(null);
    setCompileError(null);
  };

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {conditions.map((cond, i) => (
          <ConditionRow
            key={i}
            condition={cond}
            onChange={(c) => updateCondition(i, c)}
            onRemove={() => removeCondition(i)}
            columns={columns}
            resultShape={resultShape}
          />
        ))}
      </div>

      {/* NL Trigger Input */}
      {showNlInput && (
        <div className="rounded-md border border-primary/30 bg-primary/5 p-3 space-y-2">
          <div className="flex items-center gap-1.5">
            <Sparkles className="size-3.5 text-primary" />
            <span className="text-xs font-medium text-primary">AI Trigger (Beta)</span>
          </div>
          <Textarea
            placeholder="e.g. Alert when daily transaction count drops below 500"
            value={nlText}
            onChange={(e) => setNlText(e.target.value)}
            className="text-xs min-h-[60px] resize-none"
          />

          {/* Compiled preview */}
          {compiledPreview && (
            <div className="rounded border border-border bg-card p-2 space-y-1.5">
              <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Compiled Result</p>
              <p className="text-xs font-mono text-foreground">
                {compiledPreview.type}
                {compiledPreview.column && ` → ${compiledPreview.column}`}
                {compiledPreview.operator && ` ${compiledPreview.operator}`}
                {compiledPreview.value != null && ` ${compiledPreview.value}`}
                {compiledPreview.change_percent != null && ` ${compiledPreview.change_percent}%`}
              </p>
              <div className="flex gap-2 pt-1">
                <Button size="sm" className="h-6 text-xs" onClick={handleAcceptCompiled}>
                  Accept
                </Button>
                <Button size="sm" variant="outline" className="h-6 text-xs" onClick={handleCompile}>
                  Re-compile
                </Button>
              </div>
            </div>
          )}

          {compileError && (
            <p className="text-xs text-destructive">{compileError}</p>
          )}

          <div className="flex gap-2">
            {!compiledPreview && (
              <Button
                size="sm"
                className="h-7 text-xs"
                onClick={handleCompile}
                disabled={!nlText.trim() || isCompiling}
              >
                {isCompiling ? (
                  <>
                    <Loader2 className="size-3 mr-1 animate-spin" />
                    Compiling...
                  </>
                ) : (
                  "Compile"
                )}
              </Button>
            )}
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={handleCancelNl}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      <div className="flex gap-2">
        <Button type="button" variant="outline" size="sm" onClick={addCondition}>
          <Plus className="size-3.5 mr-1" />
          Add Condition
        </Button>
        {!showNlInput && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setShowNlInput(true)}
            className="border-primary/30 text-primary hover:bg-primary/10"
          >
            <Sparkles className="size-3.5 mr-1" />
            AI Trigger
            <span className="ml-1 text-[9px] font-medium bg-primary/15 text-primary px-1 py-0.5 rounded">Beta</span>
          </Button>
        )}
      </div>
    </div>
  );
}
