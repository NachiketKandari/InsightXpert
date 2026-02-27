"use client";

import { useState, useCallback, useEffect } from "react";
import { X, Workflow } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  const editingId = useAutomationStore((s) => s.editingAutomationId);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [preset, setPreset] = useState<SchedulePreset>("daily");
  const [customCron, setCustomCron] = useState("");
  const [conditions, setConditions] = useState<TriggerCondition[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);

  // Load conversation messages when builder opens
  useEffect(() => {
    if (!open) return;

    // When editing, blocks/edges are already loaded from workflow_graph
    if (editingId) {
      // Pre-populate form from the automation being edited
      const auto = useAutomationStore.getState().automations.find((a) => a.id === editingId);
      if (auto) {
        setName(auto.name);
        setDescription(auto.description ?? "");
        setConditions(auto.trigger_conditions);
      }
      // Still load messages for the sidebar query library if we have a context
      if (context) {
        const chatState = useChatStore.getState();
        const conv = chatState.conversations.find((c) => c.id === context.conversationId);
        if (conv) setMessages(conv.messages);
      }
      return;
    }

    if (!context) return;

    // Reset form for new automation
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
  }, [open, context, initBlocks, editingId]);

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

  if (!context && !editingId) return null;

  const activeBlockCount = blocks.filter((b) => b.isActive).length;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && closeBuilder()}>
      <DialogContent
        showCloseButton={false}
        className="max-w-[95vw] w-[95vw] h-[90vh] max-h-[90vh] p-0 flex flex-col gap-0 overflow-hidden"
      >
        {/* Header */}
        <DialogHeader className="px-4 py-2.5 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-3">
            {/* Brand */}
            <div className="flex items-center gap-2 flex-shrink-0">
              <div className="size-7 rounded-md bg-primary/10 flex items-center justify-center">
                <Workflow className="size-3.5 text-primary" />
              </div>
              <DialogTitle className="text-sm font-semibold whitespace-nowrap">
                Workflow Builder
              </DialogTitle>
            </div>

            <div className="h-5 w-px bg-border flex-shrink-0" />

            {/* Name */}
            <div className="w-52 flex-shrink-0 space-y-0.5">
              <Label htmlFor="wf-name" className="text-[10px] uppercase tracking-wider text-muted-foreground/60">
                Name *
              </Label>
              <Input
                id="wf-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My automation"
                className="h-7 text-sm bg-muted/30 border-transparent focus:border-border"
              />
            </div>

            {/* Description */}
            <div className="flex-1 space-y-0.5">
              <Label htmlFor="wf-desc" className="text-[10px] uppercase tracking-wider text-muted-foreground/60">
                Description
              </Label>
              <Input
                id="wf-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What does this automation monitor?"
                className="h-7 text-sm bg-muted/30 border-transparent focus:border-border"
              />
            </div>

            {/* Close */}
            <button
              onClick={closeBuilder}
              className="flex-shrink-0 p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
              aria-label="Close"
            >
              <X className="size-4" />
            </button>
          </div>
          <DialogDescription className="sr-only">
            Build an automation workflow by connecting SQL query blocks
          </DialogDescription>
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
              {isSaving ? (editingId ? "Updating..." : "Creating...") : (editingId ? "Update Automation" : "Create Automation")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
