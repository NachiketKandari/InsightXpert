"use client";

import { useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Trash2,
  Zap,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useConnectionStore } from "@/stores/connection-store";
import type {
  UserDatabaseConnection,
  TestConnectionResult,
} from "@/types/connection";

interface ConnectionCardProps {
  connection: UserDatabaseConnection;
  onDelete: (id: string) => void;
}

export function ConnectionCard({ connection, onDelete }: ConnectionCardProps) {
  const { setActive, testConnection } = useConnectionStore();
  const [expanded, setExpanded] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(
    null
  );

  const subtitle = `${connection.username}@${connection.host}:${connection.port}/${connection.database}`;

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    const result = await testConnection(connection.id);
    setTestResult(result);
    setTesting(false);
  };

  const handleToggleActive = async (checked: boolean) => {
    await setActive(connection.id, checked);
  };

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-medium truncate">{connection.name}</h3>
            {connection.is_verified ? (
              <CheckCircle2 className="size-4 text-green-500 shrink-0" />
            ) : (
              <XCircle className="size-4 text-muted-foreground/50 shrink-0" />
            )}
          </div>
          <p className="text-sm text-muted-foreground truncate font-mono mt-0.5">
            {subtitle}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Switch
            checked={connection.is_active}
            onCheckedChange={handleToggleActive}
            size="sm"
          />
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? (
              <ChevronUp className="size-4" />
            ) : (
              <ChevronDown className="size-4" />
            )}
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-border space-y-3">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-muted-foreground">Host</span>
              <p className="font-mono">{connection.host}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Port</span>
              <p className="font-mono">{connection.port}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Database</span>
              <p className="font-mono">{connection.database}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Username</span>
              <p className="font-mono">{connection.username}</p>
            </div>
          </div>

          {connection.last_verified_at && (
            <p className="text-xs text-muted-foreground">
              Last verified:{" "}
              {new Date(connection.last_verified_at).toLocaleString()}
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            Created: {new Date(connection.created_at).toLocaleString()}
          </p>

          {testResult && (
            <div
              className={`text-sm rounded-md px-3 py-2 ${
                testResult.success
                  ? "bg-green-500/10 text-green-700 dark:text-green-400"
                  : "bg-red-500/10 text-red-700 dark:text-red-400"
              }`}
            >
              {testResult.message}
              {testResult.table_count !== null && (
                <span className="ml-1">
                  ({testResult.table_count} tables found)
                </span>
              )}
            </div>
          )}

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleTest}
              disabled={testing}
            >
              {testing ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Zap className="size-3.5" />
              )}
              Test Connection
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onDelete(connection.id)}
              className="text-destructive hover:text-destructive"
            >
              <Trash2 className="size-3.5" />
              Remove
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
