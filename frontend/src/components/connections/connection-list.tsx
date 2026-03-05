"use client";

import { useEffect } from "react";
import { Database, Loader2 } from "lucide-react";
import { useConnectionStore } from "@/stores/connection-store";
import { ConnectionCard } from "./connection-card";

interface ConnectionListProps {
  onDelete: (id: string) => void;
}

export function ConnectionList({ onDelete }: ConnectionListProps) {
  const { connections, isLoading, fetchConnections } = useConnectionStore();

  useEffect(() => {
    fetchConnections();
  }, [fetchConnections]);

  if (isLoading && connections.length === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (connections.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <Database className="size-12 text-muted-foreground/50 mb-4" />
        <h3 className="text-lg font-medium">No connections yet</h3>
        <p className="text-sm text-muted-foreground mt-1 max-w-sm">
          Add a PostgreSQL database connection to query your own data with the
          AI analyst.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      {connections.map((conn) => (
        <ConnectionCard key={conn.id} connection={conn} onDelete={onDelete} />
      ))}
    </div>
  );
}
