"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Plus, PanelLeftClose, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { ConversationList } from "@/components/sidebar/conversation-list";
import { SearchResults } from "@/components/sidebar/search-results";
import { UserMenu } from "./user-menu";
import { useChatStore } from "@/stores/chat-store";
import { apiFetch } from "@/lib/api";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";

interface SearchResult {
  id: string;
  title: string;
  updated_at: string;
  title_match: boolean;
  matching_messages: { role: string; snippet: string; created_at: string }[];
}

export function LeftSidebar() {
  const newConversation = useChatStore((s) => s.newConversation);
  const toggleLeftSidebar = useChatStore((s) => s.toggleLeftSidebar);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isSearchActive = showSearch && searchQuery.length >= 2;

  const doSearch = useCallback(async (query: string) => {
    if (query.length < 2) {
      setSearchResults([]);
      setIsSearching(false);
      return;
    }
    setIsSearching(true);
    try {
      const res = await apiFetch(`/api/conversations/search?q=${encodeURIComponent(query)}`);
      if (res.ok) {
        const data = await res.json();
        setSearchResults(data);
      }
    } catch {
      // silently fail
    } finally {
      setIsSearching(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (searchQuery.length < 2) {
      setSearchResults([]);
      return;
    }
    debounceRef.current = setTimeout(() => doSearch(searchQuery), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchQuery, doSearch]);

  const handleOpenSearch = () => {
    setShowSearch(true);
    setTimeout(() => searchInputRef.current?.focus(), 50);
  };

  const handleCloseSearch = () => {
    setShowSearch(false);
    setSearchQuery("");
    setSearchResults([]);
  };

  return (
    <div className="flex flex-col h-full w-full md:w-[280px] md:max-w-[280px] glass overflow-x-hidden">
      <div className="px-4 py-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Chat History
        </h2>
        <div className="flex items-center gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                onClick={handleOpenSearch}
                aria-label="Search chats"
              >
                <Search className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Search chats</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                onClick={toggleLeftSidebar}
                aria-label="Close sidebar"
              >
                <PanelLeftClose className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Close sidebar</TooltipContent>
          </Tooltip>
        </div>
      </div>
      <Separator />

      {showSearch && (
        <>
          <div className="p-3 pb-0">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground pointer-events-none" />
              <Input
                ref={searchInputRef}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") handleCloseSearch();
                }}
                placeholder="Search chats..."
                className="h-8 pl-8 pr-8 text-sm"
              />
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={handleCloseSearch}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    aria-label="Clear search"
                  >
                    <X className="size-3.5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right">Clear search</TooltipContent>
              </Tooltip>
            </div>
          </div>
          <Separator className="mt-3" />
        </>
      )}

      {!isSearchActive && (
        <>
          <div className="p-3">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  className="w-full justify-start gap-2"
                  onClick={() => newConversation()}
                >
                  <Plus className="size-4" />
                  New Chat
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">Start a new conversation</TooltipContent>
            </Tooltip>
          </div>
          <Separator />
        </>
      )}

      <ScrollArea className="flex-1 min-h-0">
        {isSearchActive ? (
          <SearchResults
            results={searchResults}
            query={searchQuery}
            isLoading={isSearching}
          />
        ) : (
          <ConversationList />
        )}
      </ScrollArea>

      {/* User profile at sidebar bottom — like Claude / ChatGPT */}
      <UserMenu />
    </div>
  );
}
