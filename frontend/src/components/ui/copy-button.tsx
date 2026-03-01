"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

interface CopyButtonProps {
  text: string;
  className?: string;
  iconClassName?: string;
}

export function CopyButton({ text, className, iconClassName }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={cn(
        "text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-accent",
        className,
      )}
      aria-label="Copy"
    >
      {copied ? (
        <Check className={cn("size-3 text-emerald-400", iconClassName)} />
      ) : (
        <Copy className={cn("size-3", iconClassName)} />
      )}
    </button>
  );
}
