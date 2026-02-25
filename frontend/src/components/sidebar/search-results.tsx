"use client";

import { MessageSquare, FileText } from "lucide-react";
import { useChatStore } from "@/stores/chat-store";
import { cn } from "@/lib/utils";
import type { SearchResult } from "@/types/chat";

interface SearchResultsProps {
  results: SearchResult[];
  query: string;
  isLoading: boolean;
}

function highlightMatch(text: string, query: string) {
  if (!query) return text;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-cyan-accent/30 text-foreground rounded-sm px-0.5">
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}

export function SearchResults({ results, query, isLoading }: SearchResultsProps) {
  const setActiveConversation = useChatStore((s) => s.setActiveConversation);

  if (isLoading) {
    return (
      <div className="px-3 py-6 text-center">
        <div className="inline-flex items-center gap-2 text-sm text-muted-foreground">
          <div className="size-3 rounded-full border-2 border-muted-foreground/40 border-t-cyan-accent animate-spin" />
          Searching...
        </div>
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="px-3 py-8 text-center text-sm text-muted-foreground">
        No results found
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-0.5 p-2">
      <p className="px-2 pb-1 text-xs text-muted-foreground">
        {results.length} result{results.length !== 1 ? "s" : ""}
      </p>
      {results.map((result) => (
        <button
          key={result.id}
          type="button"
          onClick={() => setActiveConversation(result.id)}
          className={cn(
            "flex flex-col gap-1 w-full rounded-md px-2.5 py-2 text-left transition-colors cursor-pointer",
            "hover:bg-accent/50"
          )}
        >
          <div className="flex items-center gap-2">
            <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
            <p className="text-sm truncate flex-1">
              {highlightMatch(result.title, query)}
            </p>
          </div>
          {result.matching_messages.map((msg, i) => (
            <div
              key={i}
              className="flex items-start gap-2 ml-5.5"
            >
              <FileText className="size-3 shrink-0 text-muted-foreground/60 mt-0.5" />
              <p className="text-xs text-muted-foreground line-clamp-2">
                <span className="text-muted-foreground/70 capitalize">{msg.role}: </span>
                {highlightMatch(msg.snippet, query)}
              </p>
            </div>
          ))}
        </button>
      ))}
    </div>
  );
}
