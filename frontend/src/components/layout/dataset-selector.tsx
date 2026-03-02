"use client";

import { useState, useEffect, useCallback } from "react";
import { ChevronDown, Database, Eye, Check, Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { DatasetViewer } from "@/components/dataset/dataset-viewer";
import { CsvUploadDialog } from "@/components/dataset/csv-upload-dialog";
import { apiCall, apiFetch } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { useClientConfig } from "@/hooks/use-client-config";
import type { DatasetInfo } from "@/types/dataset";

export function DatasetSelector() {
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewingDataset, setViewingDataset] = useState<DatasetInfo | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [activatingId, setActivatingId] = useState<string | null>(null);

  const user = useAuthStore((s) => s.user);
  const { isAdmin } = useClientConfig();

  const fetchDatasets = useCallback(async () => {
    setLoading(true);
    const data = await apiCall<DatasetInfo[]>("/api/datasets/public");
    if (data) setDatasets(data);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchDatasets();
  }, [fetchDatasets]);

  // Listen for dataset-changed events fired from *any* CsvUploadDialog instance
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.id && detail?.name) {
        // Immediately update local state with the confirmed dataset
        setDatasets((prev) => {
          const exists = prev.some((d) => d.id === detail.id);
          const updated = prev.map((d) => ({ ...d, is_active: false }));
          if (exists) {
            return updated.map((d) =>
              d.id === detail.id ? { ...d, is_active: true } : d,
            );
          }
          return [
            ...updated,
            {
              id: detail.id,
              name: detail.name,
              description: detail.description ?? null,
              is_active: true,
              table_name: detail.table_name ?? null,
              created_by: detail.created_by ?? null,
            } as DatasetInfo,
          ];
        });
      } else {
        // Fallback: full refetch
        fetchDatasets();
      }
    };
    window.addEventListener("dataset-changed", handler);
    return () => window.removeEventListener("dataset-changed", handler);
  }, [fetchDatasets]);

  const activeDataset = datasets.find((d) => d.is_active);

  const handleActivate = async (ds: DatasetInfo) => {
    if (ds.is_active) return;
    setActivatingId(ds.id);
    try {
      const res = await apiFetch(`/api/datasets/${ds.id}/activate`, {
        method: "POST",
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: `Activate failed (HTTP ${res.status})` }));
        toast.error(body.detail || "Failed to activate dataset");
        return;
      }
      // Optimistically update local state so the UI reflects immediately
      setDatasets((prev) =>
        prev.map((d) => ({ ...d, is_active: d.id === ds.id }))
      );
      toast.success(`Switched to "${ds.name}"`);
    } catch {
      toast.error("Network error while activating dataset");
    } finally {
      setActivatingId(null);
    }
  };

  const handleView = (ds: DatasetInfo) => {
    setViewingDataset(ds);
    setViewerOpen(true);
  };

  const canDelete = (ds: DatasetInfo): boolean => {
    // Seeded default dataset (created_by is null) can never be deleted
    if (!ds.created_by) return false;
    if (isAdmin) return true;
    if (user && ds.created_by === user.id) return true;
    return false;
  };

  const handleDelete = async (ds: DatasetInfo) => {
    const confirmed = window.confirm(
      `Delete dataset "${ds.name}"? This action cannot be undone.`
    );
    if (!confirmed) return;

    setDeletingId(ds.id);
    try {
      const res = await apiFetch(`/api/datasets/${ds.id}`, {
        method: "DELETE",
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: `Delete failed (HTTP ${res.status})` }));
        toast.error(body.detail || "Failed to delete dataset");
        return;
      }

      toast.success(`Dataset "${ds.name}" deleted`);
      fetchDatasets();
    } catch {
      toast.error("Network error while deleting dataset");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 h-8 px-2.5 text-xs font-medium text-muted-foreground hover:text-foreground"
            disabled={loading}
          >
            {loading ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Database className="size-3.5 text-primary dark:text-cyan-accent" />
            )}
            <span className="hidden sm:inline max-w-[140px] truncate">
              {loading ? "Loading..." : (activeDataset?.name ?? "No dataset")}
            </span>
            <ChevronDown className="size-3 opacity-60" />
          </Button>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="start" className="w-72">
          {datasets.length === 0 && !loading && (
            <DropdownMenuItem disabled>No datasets found</DropdownMenuItem>
          )}
          {datasets.map((ds) => (
            <DropdownMenuItem
              key={ds.id}
              onClick={() => handleActivate(ds)}
              className="flex items-center gap-2 pr-1 cursor-pointer"
            >
              {ds.is_active ? (
                <Check className="size-3.5 shrink-0 text-primary dark:text-cyan-accent" />
              ) : activatingId === ds.id ? (
                <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
              ) : (
                <span className="size-3.5 shrink-0" />
              )}
              <span className="flex-1 truncate text-sm">{ds.name}</span>
              <div className="flex items-center gap-0.5 shrink-0">
                <Tooltip delayDuration={300}>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-6 opacity-50 hover:opacity-100 hover:bg-accent"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleView(ds);
                      }}
                      aria-label={`Preview ${ds.name}`}
                    >
                      <Eye className="size-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="right" className="text-xs">
                    Preview data &amp; columns
                  </TooltipContent>
                </Tooltip>
                {canDelete(ds) && (
                  <Tooltip delayDuration={300}>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-6 opacity-40 hover:opacity-100 hover:bg-destructive/10 hover:text-destructive"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(ds);
                        }}
                        disabled={deletingId === ds.id}
                        aria-label={`Delete ${ds.name}`}
                      >
                        {deletingId === ds.id ? (
                          <Loader2 className="size-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="size-3.5" />
                        )}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="right" className="text-xs">
                      Delete dataset
                    </TooltipContent>
                  </Tooltip>
                )}
              </div>
            </DropdownMenuItem>
          ))}

          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => setUploadOpen(true)}
            className="gap-2 cursor-pointer text-primary dark:text-cyan-accent"
          >
            <Plus className="size-3.5" />
            <span className="text-sm font-medium">Upload CSV</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <DatasetViewer
        open={viewerOpen}
        onOpenChange={setViewerOpen}
        tableName={viewingDataset?.table_name ?? "transactions"}
        datasetName={viewingDataset?.name}
        description={viewingDataset?.description}
        datasetId={viewingDataset?.id}
      />

      <CsvUploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploadSuccess={() => {}}
      />
    </>
  );
}
