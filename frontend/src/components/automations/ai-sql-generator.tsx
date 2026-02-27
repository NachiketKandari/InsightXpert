"use client";

import { useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAutomationStore } from "@/stores/automation-store";

export function AiSqlGenerator() {
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const isGenerating = useAutomationStore((s) => s.isGeneratingSQL);
  const generateSQL = useAutomationStore((s) => s.generateSQL);

  const handleGenerate = async () => {
    if (!prompt.trim() || isGenerating) return;
    setError(null);
    try {
      await generateSQL(prompt.trim());
      setPrompt("");
    } catch {
      setError("Failed to generate SQL. Try a different prompt.");
    }
  };

  return (
    <div className="space-y-2">
      <Textarea
        placeholder="Describe the query you need, e.g. 'total transactions by month'"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={3}
        className="text-sm resize-none"
      />
      {error && <p className="text-xs text-destructive">{error}</p>}
      <Button
        size="sm"
        className="w-full"
        onClick={handleGenerate}
        disabled={!prompt.trim() || isGenerating}
      >
        {isGenerating ? (
          <>
            <Loader2 className="size-3.5 mr-1.5 animate-spin" />
            Generating...
          </>
        ) : (
          <>
            <Sparkles className="size-3.5 mr-1.5" />
            Generate Block
          </>
        )}
      </Button>
    </div>
  );
}
