"use client";

import { PanelRightClose } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { ProcessSteps } from "@/components/sidebar/process-steps";
import { useChatStore } from "@/stores/chat-store";

export function RightSidebar() {
  const toggleRightSidebar = useChatStore((s) => s.toggleRightSidebar);

  return (
    <div className="flex flex-col h-full w-full md:w-[300px] md:max-w-[300px] glass overflow-x-hidden">
      <div className="px-4 py-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Agent Process
        </h2>
        <Button
          variant="ghost"
          size="icon"
          className="size-7"
          onClick={toggleRightSidebar}
          aria-label="Close agent process"
        >
          <PanelRightClose className="size-4" />
        </Button>
      </div>
      <Separator />
      <ScrollArea className="flex-1 min-h-0">
        <ProcessSteps />
      </ScrollArea>
    </div>
  );
}
