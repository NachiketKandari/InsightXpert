"use client";

import { useState, useMemo, useCallback } from "react";
import { Search, Copy, Check, MessageSquareText } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { SAMPLE_QUESTIONS } from "@/lib/sample-questions";
import { useChatStore } from "@/stores/chat-store";

interface SampleQuestionsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SampleQuestionsModal({ open, onOpenChange }: SampleQuestionsModalProps) {
  const [search, setSearch] = useState("");
  const [copiedIndex, setCopiedIndex] = useState<string | null>(null);
  const setPendingInput = useChatStore((s) => s.setPendingInput);

  const filtered = useMemo(() => {
    const term = search.toLowerCase().trim();
    if (!term) return SAMPLE_QUESTIONS;
    return SAMPLE_QUESTIONS.map((cat) => ({
      ...cat,
      questions: cat.questions.filter((q) =>
        q.toLowerCase().includes(term)
      ),
    })).filter((cat) => cat.questions.length > 0);
  }, [search]);

  const totalVisible = useMemo(
    () => filtered.reduce((sum, cat) => sum + cat.questions.length, 0),
    [filtered]
  );

  const handleSelect = useCallback(
    (question: string) => {
      setPendingInput(question);
      onOpenChange(false);
      setSearch("");
    },
    [setPendingInput, onOpenChange]
  );

  const handleCopy = useCallback(
    (question: string, key: string, e: React.MouseEvent) => {
      e.stopPropagation();
      navigator.clipboard.writeText(question);
      setCopiedIndex(key);
      setTimeout(() => setCopiedIndex(null), 1500);
    },
    []
  );

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) setSearch(""); }}>
      <DialogContent
        className="w-[95vw] max-w-4xl h-[85vh] flex flex-col p-0 bg-card border-border/60 shadow-2xl"
        showCloseButton
      >
        {/* Header */}
        <div className="px-5 pt-4 pb-3 border-b border-border/50 shrink-0 space-y-3">
          <div className="flex items-center gap-2.5">
            <div className="flex items-center justify-center size-7 rounded-md bg-primary/10 dark:bg-cyan-accent/10">
              <MessageSquareText className="size-3.5 text-primary dark:text-cyan-accent" />
            </div>
            <DialogTitle className="text-sm font-semibold tracking-wide">
              Sample Questions
            </DialogTitle>
            <Badge variant="secondary" className="text-[10px] font-medium">
              {totalVisible} questions
            </Badge>
          </div>

          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search questions..."
              className="pl-8 h-8 text-sm"
            />
          </div>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 min-h-0 overflow-y-auto px-5 py-3">
          {filtered.length === 0 ? (
            <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
              No questions match your search.
            </div>
          ) : (
            <div className="space-y-5">
              {filtered.map((cat) => (
                <section key={cat.category}>
                  <div className="sticky top-0 z-10 bg-card/95 backdrop-blur-sm pb-1.5 pt-0.5">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-primary/70 dark:text-cyan-accent/80 flex items-center gap-2">
                      {cat.category}
                      <span className="text-[10px] font-normal text-muted-foreground">
                        ({cat.questions.length})
                      </span>
                    </h3>
                  </div>
                  <div className="space-y-0.5">
                    {cat.questions.map((q, i) => {
                      const key = `${cat.category}-${i}`;
                      return (
                        <div
                          key={key}
                          onClick={() => handleSelect(q)}
                          className="group flex items-center gap-2 rounded-lg px-3 py-2 cursor-pointer hover:bg-accent/50 dark:hover:bg-accent/60 transition-colors"
                        >
                          <span className="flex-1 text-sm text-foreground/85 leading-relaxed">
                            {q}
                          </span>
                          <button
                            onClick={(e) => handleCopy(q, key, e)}
                            className="shrink-0 size-7 flex items-center justify-center rounded-md opacity-0 group-hover:opacity-100 hover:bg-accent transition-all cursor-pointer"
                            title="Copy to clipboard"
                          >
                            {copiedIndex === key ? (
                              <Check className="size-3.5 text-green-500" />
                            ) : (
                              <Copy className="size-3.5 text-muted-foreground" />
                            )}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
