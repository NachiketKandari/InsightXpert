"use client";

import { useState, useEffect } from "react";
import { ChevronDown, Database, Eye, Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { DatasetViewer } from "@/components/dataset/dataset-viewer";
import { apiCall } from "@/lib/api";

interface DatasetInfo {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  table_name: string | null;
}

export function DatasetSelector() {
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewingDataset, setViewingDataset] = useState<DatasetInfo | null>(null);

  useEffect(() => {
    apiCall<DatasetInfo[]>("/api/datasets/public")
      .then((data) => { if (data) setDatasets(data); })
      .finally(() => setLoading(false));
  }, []);

  const activeDataset = datasets.find((d) => d.is_active);

  const handleView = (ds: DatasetInfo, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setViewingDataset(ds);
    setViewerOpen(true);
  };

  const handleActivate = async (ds: DatasetInfo) => {
    if (ds.is_active) return;
    const ok = await apiCall(`/api/datasets/${ds.id}/activate`, { method: "POST" });
    if (ok !== null) {
      setDatasets((prev) => prev.map((d) => ({ ...d, is_active: d.id === ds.id })));
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
              {loading ? "Loading…" : (activeDataset?.name ?? "No dataset")}
            </span>
            <ChevronDown className="size-3 opacity-60" />
          </Button>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="start" className="w-64">
          {datasets.length === 0 && !loading && (
            <DropdownMenuItem disabled>No datasets found</DropdownMenuItem>
          )}
          {datasets.map((ds) => (
            <Tooltip key={ds.id} delayDuration={400}>
              <TooltipTrigger asChild>
                <DropdownMenuItem
                  onClick={() => handleActivate(ds)}
                  className="flex items-center gap-2 pr-1 cursor-pointer"
                >
                  {ds.is_active ? (
                    <Check className="size-3.5 shrink-0 text-primary dark:text-cyan-accent" />
                  ) : (
                    <span className="size-3.5 shrink-0" />
                  )}
                  <span className="flex-1 truncate text-sm">{ds.name}</span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-6 shrink-0 opacity-50 hover:opacity-100 hover:bg-accent"
                    onClick={(e) => handleView(ds, e)}
                    aria-label={`Preview ${ds.name}`}
                  >
                    <Eye className="size-3.5" />
                  </Button>
                </DropdownMenuItem>
              </TooltipTrigger>
              {ds.description && (
                <TooltipContent side="right" className="max-w-56 text-xs">
                  {ds.description}
                </TooltipContent>
              )}
            </Tooltip>
          ))}
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
    </>
  );
}
