"use client";

import { useEffect } from "react";
import { ChevronsUpDown } from "lucide-react";
import { useSettingsStore } from "@/stores/settings-store";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";

const PROVIDER_LABELS: Record<string, string> = {
  gemini: "Gemini",
  ollama: "Ollama",
};

/** Strip provider prefix and title-case: "gemini-2.5-flash" → "2.5 Flash" */
function formatModelName(model: string, provider: string): string {
  let name = model;
  // Strip provider prefix (e.g. "gemini-", "ollama/")
  const prefixes = [provider + "-", provider + "/"];
  for (const p of prefixes) {
    if (name.toLowerCase().startsWith(p)) {
      name = name.slice(p.length);
      break;
    }
  }
  // Replace hyphens/underscores with spaces and title-case each word
  return name
    .replace(/[-_]/g, " ")
    .replace(/\b[a-z]/g, (c) => c.toUpperCase());
}

export function ModelSelector() {
  const {
    currentProvider,
    currentModel,
    providers,
    loading,
    fetchConfig,
    switchModel,
  } = useSettingsStore();

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const currentProviderModels =
    providers.find((p) => p.provider === currentProvider)?.models ?? [];

  const handleProviderChange = (provider: string) => {
    if (provider === currentProvider) return;
    const firstModel =
      providers.find((p) => p.provider === provider)?.models[0] ?? "";
    switchModel(provider, firstModel);
  };

  const handleModelChange = (model: string) => {
    if (model === currentModel) return;
    switchModel(currentProvider, model);
  };

  const providerLabel = PROVIDER_LABELS[currentProvider] ?? currentProvider;

  const displayModel = formatModelName(currentModel, currentProvider);

  return (
    <div className="flex items-center gap-1 text-sm">
      {/* Provider selector - hidden on mobile to save space */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className="flex items-center gap-1.5 rounded-md px-2 md:px-2.5 py-1.5 text-xs md:text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors outline-none disabled:opacity-50"
            disabled={loading}
          >
            <span className="hidden md:inline">{providerLabel}</span>
            <span className="md:hidden">{providerLabel.slice(0, 3)}</span>
            <ChevronsUpDown className="size-3.5 opacity-50" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="min-w-[140px]">
          <DropdownMenuLabel className="text-xs text-muted-foreground">
            Provider
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuRadioGroup
            value={currentProvider}
            onValueChange={handleProviderChange}
          >
            {providers.map((p) => (
              <DropdownMenuRadioItem key={p.provider} value={p.provider}>
                {PROVIDER_LABELS[p.provider] ?? p.provider}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      <span className="text-muted-foreground/40 select-none">/</span>

      {/* Model selector */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className="flex items-center gap-1.5 rounded-md px-2 md:px-2.5 py-1.5 text-xs md:text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors outline-none disabled:opacity-50 max-w-[120px] md:max-w-none"
            disabled={loading}
          >
            <span className="truncate">{displayModel}</span>
            <ChevronsUpDown className="size-3.5 opacity-50 shrink-0" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="min-w-[200px]">
          <DropdownMenuLabel className="text-xs text-muted-foreground">
            Model
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuRadioGroup
            value={currentModel}
            onValueChange={handleModelChange}
          >
            {currentProviderModels.map((model) => (
              <DropdownMenuRadioItem key={model} value={model}>
                {formatModelName(model, currentProvider)}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
