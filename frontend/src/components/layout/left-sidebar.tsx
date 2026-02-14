"use client";

import { Plus, PanelLeftClose } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { ConversationList } from "@/components/sidebar/conversation-list";
import { useChatStore } from "@/stores/chat-store";

export function LeftSidebar() {
  const newConversation = useChatStore((s) => s.newConversation);
  const toggleLeftSidebar = useChatStore((s) => s.toggleLeftSidebar);

  return (
    <div className="flex flex-col h-full w-[280px] max-w-[280px] glass overflow-x-hidden">
      <div className="px-4 py-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Chat History
        </h2>
        <Button
          variant="ghost"
          size="icon"
          className="size-7"
          onClick={toggleLeftSidebar}
          aria-label="Close chat history"
        >
          <PanelLeftClose className="size-4" />
        </Button>
      </div>
      <Separator />
      <div className="p-3">
        <Button
          variant="outline"
          className="w-full justify-start gap-2"
          onClick={() => newConversation()}
        >
          <Plus className="size-4" />
          New Chat
        </Button>
      </div>
      <Separator />
      <ScrollArea className="flex-1 min-h-0">
        <ConversationList />
      </ScrollArea>
    </div>
  );
}
