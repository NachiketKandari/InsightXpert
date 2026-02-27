"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sun, Moon, Monitor } from "lucide-react";
import type { OrgBranding } from "@/types/admin";

const COLOR_MODES: { value: "dark" | "light" | null; label: string; icon: React.ElementType }[] = [
  { value: null, label: "Auto", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

const THEME_COLORS: { key: string; label: string }[] = [
  { key: "--background", label: "Background" },
  { key: "--foreground", label: "Foreground" },
  { key: "--primary", label: "Primary" },
  { key: "--primary-foreground", label: "Primary Foreground" },
  { key: "--secondary", label: "Secondary" },
  { key: "--secondary-foreground", label: "Secondary Foreground" },
  { key: "--muted", label: "Muted" },
  { key: "--muted-foreground", label: "Muted Foreground" },
  { key: "--accent", label: "Accent" },
  { key: "--accent-foreground", label: "Accent Foreground" },
  { key: "--border", label: "Border" },
  { key: "--card", label: "Card" },
  { key: "--card-foreground", label: "Card Foreground" },
];

interface BrandingEditorProps {
  branding: OrgBranding;
  onChange: (branding: OrgBranding) => void;
}

export function BrandingEditor({ branding, onChange }: BrandingEditorProps) {
  const update = (patch: Partial<OrgBranding>) => {
    onChange({ ...branding, ...patch });
  };

  const updateThemeColor = (key: string, value: string) => {
    const theme = { ...(branding.theme ?? {}) };
    if (value) {
      theme[key] = value;
    } else {
      delete theme[key];
    }
    update({ theme: Object.keys(theme).length > 0 ? theme : null });
  };

  return (
    <div className="space-y-6">
      <h3 className="text-sm font-medium text-muted-foreground">
        Branding & Theme
      </h3>

      {/* Color Mode */}
      <div className="space-y-2">
        <Label>Color Mode</Label>
        <div className="flex gap-2">
          {COLOR_MODES.map(({ value, label, icon: Icon }) => {
            const active = branding.color_mode === value;
            return (
              <button
                key={String(value)}
                type="button"
                onClick={() => update({ color_mode: value })}
                className={`flex items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors ${
                  active
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-transparent text-muted-foreground hover:border-primary/50 hover:text-foreground"
                }`}
              >
                <Icon className="size-4" />
                {label}
              </button>
            );
          })}
        </div>
        <p className="text-xs text-muted-foreground">
          Auto follows the user&apos;s system/browser preference.
        </p>
      </div>

      {/* Identity */}
      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="display_name">Display Name</Label>
          <Input
            id="display_name"
            placeholder="e.g. Acme Analytics"
            value={branding.display_name ?? ""}
            onChange={(e) =>
              update({ display_name: e.target.value || null })
            }
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="logo_url">Logo URL</Label>
          <Input
            id="logo_url"
            placeholder="https://example.com/logo.svg"
            value={branding.logo_url ?? ""}
            onChange={(e) =>
              update({ logo_url: e.target.value || null })
            }
          />
          {branding.logo_url && (
            <div className="mt-2 flex items-center gap-2 rounded border border-border p-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={branding.logo_url}
                alt="Logo preview"
                className="h-8 w-auto object-contain"
                onError={(e) =>
                  ((e.target as HTMLImageElement).style.display = "none")
                }
              />
              <span className="text-xs text-muted-foreground">Preview</span>
            </div>
          )}
        </div>
      </div>

      {/* Color Theme */}
      <div className="space-y-3">
        <h4 className="text-sm font-medium">Color Theme (CSS Variables)</h4>
        <p className="text-xs text-muted-foreground">
          Override CSS color variables for this organization. Leave empty to use
          defaults.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {THEME_COLORS.map(({ key, label }) => (
            <div key={key} className="flex items-center gap-2">
              <div
                className="size-6 shrink-0 rounded border border-border"
                style={{
                  backgroundColor: branding.theme?.[key] || "transparent",
                }}
              />
              <div className="flex-1">
                <Label htmlFor={`theme-${key}`} className="text-xs">
                  {label}
                </Label>
                <Input
                  id={`theme-${key}`}
                  className="h-8 text-xs"
                  placeholder={key}
                  value={branding.theme?.[key] ?? ""}
                  onChange={(e) => updateThemeColor(key, e.target.value)}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
