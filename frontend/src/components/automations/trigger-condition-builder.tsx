"use client";

import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
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

  return (
    <div className="space-y-3">
      <Label className="text-sm font-medium">Trigger Conditions</Label>
      <p className="text-xs text-muted-foreground">
        Define when notifications should fire. Leave empty to notify on every run.
      </p>
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
      <Button type="button" variant="outline" size="sm" onClick={addCondition}>
        <Plus className="size-3.5 mr-1" />
        Add Condition
      </Button>
    </div>
  );
}
