"use client";

import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { OPERATOR_LABELS } from "@/lib/automation-utils";
import type { TriggerCondition } from "@/types/automation";
import type { ResultShape } from "@/lib/automation-utils";

interface ConditionRowProps {
  condition: TriggerCondition;
  onChange: (condition: TriggerCondition) => void;
  onRemove: () => void;
  columns: string[];
  resultShape: ResultShape;
}

const needsColumn = (type: string, resultShape: ResultShape) =>
  type === "column_expression" ||
  type === "slope" ||
  (type === "threshold" && resultShape !== "scalar");

const needsOperator = (type: string) =>
  type === "threshold" || type === "column_expression" || type === "row_count" || type === "slope";

const needsValue = (type: string) =>
  type === "threshold" || type === "column_expression" || type === "row_count" || type === "slope";

export function ConditionRow({ condition, onChange, onRemove, columns, resultShape }: ConditionRowProps) {
  const availableTypes = getAvailableTypes(resultShape);

  return (
    <div className="flex items-start gap-2 rounded-md border border-border p-3">
      <div className="flex-1 space-y-2">
        <div className="flex flex-wrap gap-2">
          {/* Condition type */}
          <Select
            value={condition.type}
            onValueChange={(v) =>
              onChange({
                ...condition,
                type: v as TriggerCondition["type"],
                column: null,
                operator: null,
                value: null,
                change_percent: null,
                scope: null,
                slope_window: v === "slope" ? 5 : null,
              })
            }
          >
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {availableTypes.map((t) => (
                <SelectItem key={t.value} value={t.value}>
                  {t.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Column selector */}
          {needsColumn(condition.type, resultShape) && (
            <Select
              value={condition.column ?? ""}
              onValueChange={(v) => onChange({ ...condition, column: v })}
            >
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder="Column" />
              </SelectTrigger>
              <SelectContent>
                {columns.map((col) => (
                  <SelectItem key={col} value={col}>
                    {col}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          {/* Operator */}
          {needsOperator(condition.type) && (
            <Select
              value={condition.operator ?? ""}
              onValueChange={(v) => onChange({ ...condition, operator: v })}
            >
              <SelectTrigger className="w-[80px]">
                <SelectValue placeholder="Op" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(OPERATOR_LABELS).map(([key, label]) => (
                  <SelectItem key={key} value={key}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          {/* Value */}
          {needsValue(condition.type) && (
            <Input
              type="number"
              placeholder="Value"
              className="w-[100px]"
              value={condition.value ?? ""}
              onChange={(e) =>
                onChange({ ...condition, value: e.target.value ? Number(e.target.value) : null })
              }
            />
          )}

          {/* Change percent */}
          {condition.type === "change_detection" && (
            <div className="flex items-center gap-1">
              <Input
                type="number"
                placeholder="%"
                className="w-[80px]"
                value={condition.change_percent ?? ""}
                onChange={(e) =>
                  onChange({
                    ...condition,
                    change_percent: e.target.value ? Number(e.target.value) : null,
                  })
                }
              />
              <span className="text-xs text-muted-foreground">% change</span>
            </div>
          )}

          {/* Slope window */}
          {condition.type === "slope" && (
            <div className="flex items-center gap-1">
              <Input
                type="number"
                placeholder="5"
                className="w-[60px]"
                min={2}
                max={50}
                value={condition.slope_window ?? 5}
                onChange={(e) =>
                  onChange({
                    ...condition,
                    slope_window: e.target.value ? Number(e.target.value) : 5,
                  })
                }
              />
              <span className="text-xs text-muted-foreground">runs</span>
            </div>
          )}

          {/* Scope selector for column_expression on tabular */}
          {condition.type === "column_expression" && resultShape === "tabular" && (
            <Select
              value={condition.scope ?? "any_row"}
              onValueChange={(v) =>
                onChange({ ...condition, scope: v as "any_row" | "all_rows" })
              }
            >
              <SelectTrigger className="w-[120px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="any_row">Any row</SelectItem>
                <SelectItem value="all_rows">All rows</SelectItem>
              </SelectContent>
            </Select>
          )}
        </div>

        {/* Condition type description */}
        <p className="text-[10px] text-muted-foreground/70 leading-tight">
          {getConditionHint(condition.type)}
        </p>
      </div>

      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="size-8 shrink-0 text-muted-foreground hover:text-destructive"
        onClick={onRemove}
      >
        <Trash2 className="size-3.5" />
      </Button>
    </div>
  );
}

function getAvailableTypes(resultShape: ResultShape) {
  // All condition types are available for all result shapes.
  // row_count works universally (count of result rows).
  // slope and change_detection compare across runs.
  const types = [
    { value: "threshold", label: "Value" },
    { value: "row_count", label: "Row Count" },
    { value: "change_detection", label: "Change %" },
    { value: "slope", label: "Slope / Trend" },
  ];
  if (resultShape === "tabular" || resultShape === "single_row") {
    types.push({ value: "column_expression", label: "Column Condition" });
  }
  return types;
}

function getConditionHint(type: string): string {
  switch (type) {
    case "threshold":
      return "Compare the result value against a threshold.";
    case "row_count":
      return "Compare the number of result rows against a threshold.";
    case "change_detection":
      return "Fire when value changes by more than N% from the previous run.";
    case "slope":
      return "Compute the rate of change (linear slope) across recent runs. Use to detect trends.";
    case "column_expression":
      return "Check a column value across rows (any row or all rows must match).";
    default:
      return "";
  }
}
