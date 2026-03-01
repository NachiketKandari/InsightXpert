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

  const handleView = (ds: DatasetInfo) => {
    setViewingDataset(ds);
    setViewerOpen(true);
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
            <DropdownMenuItem
              key={ds.id}
              onClick={() => handleView(ds)}
              className="flex items-center gap-2 pr-1 cursor-pointer"
            >
              {ds.is_active ? (
                <Check className="size-3.5 shrink-0 text-primary dark:text-cyan-accent" />
              ) : (
                <span className="size-3.5 shrink-0" />
              )}
              <span className="flex-1 truncate text-sm">{ds.name}</span>
              <Tooltip delayDuration={300}>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-6 shrink-0 opacity-50 hover:opacity-100 hover:bg-accent"
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
            </DropdownMenuItem>
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
