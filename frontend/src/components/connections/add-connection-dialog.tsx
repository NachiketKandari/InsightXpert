"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useConnectionStore } from "@/stores/connection-store";

interface AddConnectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddConnectionDialog({
  open,
  onOpenChange,
}: AddConnectionDialogProps) {
  const { createConnection, testConnection } = useConnectionStore();
  const [name, setName] = useState("");
  const [connectionString, setConnectionString] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const isValidConnectionString =
    connectionString.startsWith("postgresql://") ||
    connectionString.startsWith("postgres://");

  const canSubmit = name.trim() && isValidConnectionString && !isSubmitting;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    setError(null);
    setIsSubmitting(true);
    setStatus("Creating connection...");

    const conn = await createConnection({
      name: name.trim(),
      connection_string: connectionString.trim(),
    });

    if (!conn) {
      setError("Failed to create connection. Check your connection string.");
      setIsSubmitting(false);
      setStatus(null);
      return;
    }

    setStatus("Testing connection...");
    await testConnection(conn.id);

    setIsSubmitting(false);
    setStatus(null);
    setName("");
    setConnectionString("");
    onOpenChange(false);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!isSubmitting) {
      if (!nextOpen) {
        setName("");
        setConnectionString("");
        setError(null);
        setStatus(null);
      }
      onOpenChange(nextOpen);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Database Connection</DialogTitle>
          <DialogDescription>
            Connect a PostgreSQL database to query with the AI analyst.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 px-4 pb-4">
          <div className="space-y-1.5">
            <label
              htmlFor="conn-name"
              className="text-sm font-medium leading-none"
            >
              Name
            </label>
            <input
              id="conn-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Production DB"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              disabled={isSubmitting}
            />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="conn-string"
              className="text-sm font-medium leading-none"
            >
              Connection String
            </label>
            <textarea
              id="conn-string"
              value={connectionString}
              onChange={(e) => setConnectionString(e.target.value)}
              placeholder="postgresql://user:password@host:5432/dbname"
              rows={3}
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm font-mono shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
              disabled={isSubmitting}
            />
            {connectionString && !isValidConnectionString && (
              <p className="text-xs text-destructive">
                Connection string must start with postgresql:// or postgres://
              </p>
            )}
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          {status && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" />
              {status}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {isSubmitting ? (
                <Loader2 className="size-4 animate-spin" />
              ) : null}
              Add Connection
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
