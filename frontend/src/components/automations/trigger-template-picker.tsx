"use client";

import { useState, useCallback } from "react";
import { Save, FolderOpen, Trash2, ChevronDown, X, Loader2 } from "lucide-react";
import { useAutomationStore } from "@/stores/automation-store";
import type { TriggerCondition } from "@/types/automation";

interface TriggerTemplatePickerProps {
  conditions: TriggerCondition[];
  onConditionsChange: (conditions: TriggerCondition[]) => void;
}

export function TriggerTemplatePicker({
  conditions,
  onConditionsChange,
}: TriggerTemplatePickerProps) {
  const templates = useAutomationStore((s) => s.triggerTemplates);
  const isLoading = useAutomationStore((s) => s.isLoadingTemplates);
  const createTemplate = useAutomationStore((s) => s.createTriggerTemplate);
  const deleteTemplate = useAutomationStore((s) => s.deleteTriggerTemplate);

  const [showSaveInput, setShowSaveInput] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);

  const handleSave = useCallback(async () => {
    if (!saveName.trim() || conditions.length === 0) return;
    setIsSaving(true);
    await createTemplate(saveName.trim(), null, conditions);
    setIsSaving(false);
    setSaveName("");
    setShowSaveInput(false);
  }, [saveName, conditions, createTemplate]);

  const handleLoad = useCallback(
    (templateConditions: TriggerCondition[]) => {
      onConditionsChange(templateConditions);
      setShowDropdown(false);
    },
    [onConditionsChange],
  );

  const handleDelete = useCallback(
    async (e: React.MouseEvent, id: string) => {
      e.stopPropagation();
      await deleteTemplate(id);
    },
    [deleteTemplate],
  );

  return (
    <div className="flex items-center gap-1.5 mb-2">
      {/* Load Template */}
      <div className="relative">
        <button
          onClick={() => setShowDropdown(!showDropdown)}
          disabled={isLoading || templates.length === 0}
          className="inline-flex items-center gap-1 px-2 py-1 text-[10px] font-medium text-muted-foreground hover:text-foreground bg-muted/30 hover:bg-muted/50 border border-border/60 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <FolderOpen className="size-3" />
          Load
          <ChevronDown className="size-2.5" />
        </button>

        {showDropdown && templates.length > 0 && (
          <>
            {/* Backdrop */}
            <div
              className="fixed inset-0 z-40"
              onClick={() => setShowDropdown(false)}
            />
            {/* Dropdown */}
            <div className="absolute left-0 top-full mt-1 z-50 w-56 bg-popover border border-border rounded-lg shadow-lg overflow-hidden">
              <div className="max-h-48 overflow-y-auto">
                {templates.map((tpl) => (
                  <button
                    key={tpl.id}
                    onClick={() => handleLoad(tpl.conditions)}
                    className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-xs hover:bg-muted/50 transition-colors group"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">{tpl.name}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {tpl.conditions.length} condition{tpl.conditions.length !== 1 ? "s" : ""}
                      </p>
                    </div>
                    <button
                      onClick={(e) => handleDelete(e, tpl.id)}
                      className="opacity-0 group-hover:opacity-100 p-0.5 text-muted-foreground hover:text-destructive transition-all"
                      title="Delete template"
                    >
                      <Trash2 className="size-3" />
                    </button>
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Save as Template */}
      {conditions.length > 0 && !showSaveInput && (
        <button
          onClick={() => setShowSaveInput(true)}
          className="inline-flex items-center gap-1 px-2 py-1 text-[10px] font-medium text-muted-foreground hover:text-foreground bg-muted/30 hover:bg-muted/50 border border-border/60 rounded-md transition-colors"
        >
          <Save className="size-3" />
          Save as Template
        </button>
      )}

      {/* Inline save input */}
      {showSaveInput && (
        <div className="flex items-center gap-1 flex-1">
          <input
            autoFocus
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSave();
              if (e.key === "Escape") {
                setShowSaveInput(false);
                setSaveName("");
              }
            }}
            placeholder="Template name"
            className="flex-1 h-6 px-2 text-[11px] bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-primary/50"
          />
          <button
            onClick={handleSave}
            disabled={!saveName.trim() || isSaving}
            className="p-1 text-primary hover:text-primary/80 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isSaving ? <Loader2 className="size-3 animate-spin" /> : <Save className="size-3" />}
          </button>
          <button
            onClick={() => {
              setShowSaveInput(false);
              setSaveName("");
            }}
            className="p-1 text-muted-foreground hover:text-foreground"
          >
            <X className="size-3" />
          </button>
        </div>
      )}
    </div>
  );
}
