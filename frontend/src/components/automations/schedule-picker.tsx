"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cronToHumanReadable, SCHEDULE_PRESETS } from "@/lib/automation-utils";
import type { SchedulePreset } from "@/types/automation";

interface SchedulePickerProps {
  preset: SchedulePreset;
  customCron: string;
  onChange: (preset: SchedulePreset, customCron: string) => void;
}

const PRESET_LABELS: Record<string, string> = {
  hourly: "Hourly",
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
  custom: "Custom",
};

export function SchedulePicker({ preset, customCron, onChange }: SchedulePickerProps) {
  const presets: SchedulePreset[] = ["hourly", "daily", "weekly", "monthly", "custom"];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {presets.map((p) => (
          <Button
            key={p}
            type="button"
            variant={preset === p ? "default" : "outline"}
            size="sm"
            onClick={() => onChange(p, customCron)}
          >
            {PRESET_LABELS[p]}
          </Button>
        ))}
      </div>
      {preset === "custom" ? (
        <div className="space-y-1.5">
          <Input
            placeholder="0 9 * * 1-5"
            value={customCron}
            onChange={(e) => onChange("custom", e.target.value)}
          />
          {customCron && (
            <p className="text-xs text-muted-foreground">
              {cronToHumanReadable(customCron)}
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          {cronToHumanReadable(
            SCHEDULE_PRESETS[preset as keyof typeof SCHEDULE_PRESETS] ?? ""
          )}
        </p>
      )}
    </div>
  );
}
