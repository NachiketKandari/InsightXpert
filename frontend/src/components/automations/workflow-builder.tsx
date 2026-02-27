"use client";

import { useState, useCallback, useEffect } from "react";
import { X } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { useChatStore } from "@/stores/chat-store";
import { useAutomationStore } from "@/stores/automation-store";
import { WorkflowSidebar } from "./workflow-sidebar";
import { WorkflowCanvas } from "./workflow-canvas";
import type { TriggerCondition, SchedulePreset } from "@/types/automation";
import type { Message } from "@/types/chat";

export function WorkflowBuilder() {
  const open = useAutomationStore((s) => s.workflowBuilderOpen);
  const context = useAutomationStore((s) => s.workflowBuilderContext);
  const closeBuilder = useAutomationStore((s) => s.closeWorkflowBuilder);
  const initBlocks = useAutomationStore((s) => s.initBlocksFromConversation);
  const saveWorkflow = useAutomationStore((s) => s.saveWorkflowAsAutomation);
  const blocks = useAutomationStore((s) => s.workflowBlocks);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [preset, setPreset] = useState<SchedulePreset>("daily");
  const [customCron, setCustomCron] = useState("");
  const [conditions, setConditions] = useState<TriggerCondition[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);

  // Load conversation messages when builder opens
  useEffect(() => {
    if (!open || !context) return;

    // Reset form
    setName("");
    setDescription("");
    setPreset("daily");
    setCustomCron("");
    setConditions([]);

    // Get messages from the chat store
    const chatState = useChatStore.getState();
    const conv = chatState.conversations.find((c) => c.id === context.conversationId);

    if (conv && conv.messages.length > 0) {
      setMessages(conv.messages);
      initBlocks(conv.messages, context.focusMessageId);
    } else {
      // Need to load conversation messages first
      chatState.loadConversationMessages(context.conversationId).then(() => {
        const updatedConv = useChatStore
          .getState()
          .conversations.find((c) => c.id === context.conversationId);
        if (updatedConv) {
          setMessages(updatedConv.messages);
          initBlocks(updatedConv.messages, context.focusMessageId);
        }
      });
    }
  }, [open, context, initBlocks]);

  const handleScheduleChange = useCallback((p: SchedulePreset, cron: string) => {
    setPreset(p);
    setCustomCron(cron);
  }, []);

  const handleSave = async () => {
    if (!name.trim() || blocks.filter((b) => b.isActive).length === 0) return;
    setIsSaving(true);

    const result = await saveWorkflow({
      name: name.trim(),
      description: description.trim() || undefined,
      schedulePreset: preset === "custom" ? undefined : preset,
      cronExpression: preset === "custom" ? customCron : undefined,
      triggerConditions: conditions,
    });

    setIsSaving(false);
    if (result) {
      closeBuilder();
    }
  };

  if (!context) return null;

  const activeBlockCount = blocks.filter((b) => b.isActive).length;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && closeBuilder()}>
      <DialogContent className="max-w-[95vw] w-[95vw] h-[90vh] max-h-[90vh] p-0 flex flex-col gap-0 overflow-hidden">
        {/* Header */}
        <DialogHeader className="px-4 py-3 border-b border-border flex-shrink-0">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 space-y-2">
              <DialogTitle className="sr-only">Workflow Builder</DialogTitle>
              <DialogDescription className="sr-only">
                Build an automation workflow by connecting SQL query blocks
              </DialogDescription>
              <div className="flex items-center gap-3">
                <div className="flex-1 space-y-1">
                  <Label htmlFor="wf-name" className="text-xs text-muted-foreground">
                    Name
                  </Label>
                  <Input
                    id="wf-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Automation name"
                    className="h-8 text-sm"
                  />
                </div>
                <div className="flex-1 space-y-1">
                  <Label htmlFor="wf-desc" className="text-xs text-muted-foreground">
                    Description (optional)
                  </Label>
                  <Textarea
                    id="wf-desc"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="What does this automation monitor?"
                    rows={1}
                    className="text-sm resize-none min-h-[32px]"
                  />
                </div>
              </div>
            </div>
            <button
              onClick={closeBuilder}
              className="p-1 rounded-md text-muted-foreground hover:text-foreground transition-colors mt-1"
            >
              <X className="size-4" />
            </button>
          </div>
        </DialogHeader>

        {/* Body: Sidebar + Canvas */}
        <div className="flex flex-1 overflow-hidden">
          <WorkflowSidebar
            messages={messages}
            preset={preset}
            customCron={customCron}
            onScheduleChange={handleScheduleChange}
            conditions={conditions}
            onConditionsChange={setConditions}
          />
          <div className="flex-1 min-w-0">
            <WorkflowCanvas />
          </div>
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-border flex items-center justify-between flex-shrink-0">
          <span className="text-xs text-muted-foreground">
            {activeBlockCount} active block{activeBlockCount !== 1 ? "s" : ""}
            {blocks.some((b) => b.isEndpoint) && " \u00b7 Endpoint set"}
          </span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={closeBuilder}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={!name.trim() || activeBlockCount === 0 || isSaving}
            >
              {isSaving ? "Creating..." : "Create Automation"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
