"use client";

import { useCallback } from "react";
import Link from "next/link";
import { ArrowLeft, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAutomationStore } from "@/stores/automation-store";
import { AutomationList } from "@/components/automations/automation-list";
import { WorkflowBuilder } from "@/components/automations/workflow-builder";
import { useConfirm } from "@/components/ui/confirm-dialog";

export default function AutomationsPage() {
  const deleteAutomation = useAutomationStore((s) => s.deleteAutomation);
  const openWorkflowBuilder = useAutomationStore((s) => s.openWorkflowBuilder);
  const { confirm, ConfirmDialog } = useConfirm();

  const handleDelete = useCallback(
    async (id: string) => {
      const ok = await confirm({
        title: "Delete automation",
        description: "Are you sure? This will stop all scheduled runs and cannot be undone.",
        confirmLabel: "Delete",
        variant: "destructive",
      });
      if (ok) {
        await deleteAutomation(id);
      }
    },
    [confirm, deleteAutomation]
  );

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-10 glass border-b border-border px-4 py-3 sm:px-6">
        <div className="mx-auto flex max-w-5xl items-center gap-3">
          <Link href="/">
            <Button variant="ghost" size="icon" className="size-9">
              <ArrowLeft className="size-4" />
            </Button>
          </Link>
          <h1 className="text-lg font-semibold">Automations</h1>
          <div className="ml-auto">
            <Button size="sm" onClick={() => openWorkflowBuilder()}>
              <Plus className="size-4 mr-1.5" />
              New automation
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        <AutomationList onDelete={handleDelete} onNew={() => openWorkflowBuilder()} />
      </main>

      <ConfirmDialog />
      <WorkflowBuilder />
    </div>
  );
}
