"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { ArrowLeft, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useConnectionStore } from "@/stores/connection-store";
import { ConnectionList } from "@/components/connections/connection-list";
import { AddConnectionDialog } from "@/components/connections/add-connection-dialog";
import { useConfirm } from "@/components/ui/confirm-dialog";

export default function ConnectionsPage() {
  const deleteConnection = useConnectionStore((s) => s.deleteConnection);
  const { confirm, ConfirmDialog } = useConfirm();
  const [addDialogOpen, setAddDialogOpen] = useState(false);

  const handleDelete = useCallback(
    async (id: string) => {
      const ok = await confirm({
        title: "Remove connection",
        description:
          "Are you sure? This will remove the database connection and cannot be undone.",
        confirmLabel: "Remove",
        variant: "destructive",
      });
      if (ok) {
        await deleteConnection(id);
      }
    },
    [confirm, deleteConnection]
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
          <h1 className="text-lg font-semibold flex-1">My Connections</h1>
          <Button size="sm" onClick={() => setAddDialogOpen(true)}>
            <Plus className="size-4" />
            Add Connection
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        <ConnectionList onDelete={handleDelete} />
      </main>

      <ConfirmDialog />
      <AddConnectionDialog
        open={addDialogOpen}
        onOpenChange={setAddDialogOpen}
      />
    </div>
  );
}
