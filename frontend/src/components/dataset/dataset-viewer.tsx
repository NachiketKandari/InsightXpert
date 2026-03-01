"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Loader2,
  Rows3,
  AlertTriangle,
  Database,
  Code2,
  Copy,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DataTable } from "@/components/chunks/data-table";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { apiFetch, apiCall } from "@/lib/api";
import { downloadCsv } from "@/lib/utils";
import type { QueryResult } from "@/types/api";

const PAGE_SIZE = 100;

interface DatasetViewerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tableName?: string;
  datasetName?: string;
}

export function DatasetViewer({ open, onOpenChange, tableName = "transactions", datasetName = "Dataset Viewer" }: DatasetViewerProps) {
  const [activeTab, setActiveTab] = useState<string>("data");
  const [data, setData] = useState<QueryResult | null>(null);
  const [totalRows, setTotalRows] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Schema/DDL state
  const [ddl, setDdl] = useState<string | null>(null);
  const [ddlLoading, setDdlLoading] = useState(false);
  const [ddlError, setDdlError] = useState<string | null>(null);
  const [ddlCopied, setDdlCopied] = useState(false);

  const fetchPage = useCallback(async (pageOffset: number) => {
    setLoading(true);
    setError(null);

    try {
      const res = await apiFetch("/api/sql/execute", {
        method: "POST",
        body: JSON.stringify({
          sql: `SELECT * FROM ${tableName} LIMIT ${PAGE_SIZE} OFFSET ${pageOffset}`,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        setError(body.detail || `HTTP ${res.status}`);
        return;
      }

      const result: QueryResult = await res.json();
      setData(result);
      scrollRef.current?.scrollTo({ top: 0 });
    } catch (err) {
      setError((err as Error).message || "Network error");
    } finally {
      setLoading(false);
    }
  }, [tableName]);

  const fetchTotalCount = useCallback(async () => {
    const result = await apiCall<QueryResult>("/api/sql/execute", {
      method: "POST",
      body: JSON.stringify({
        sql: `SELECT COUNT(*) as total FROM ${tableName}`,
      }),
    });
    if (result && result.rows.length > 0) {
      setTotalRows(Number(result.rows[0].total));
    }
  }, [tableName]);

  const fetchDdl = useCallback(async () => {
    setDdlLoading(true);
    setDdlError(null);
    try {
      const result = await apiCall<{ ddl: string; tables: string[] }>("/api/schema");
      if (result) {
        setDdl(result.ddl);
      }
    } catch (err) {
      setDdlError((err as Error).message || "Failed to load schema");
    } finally {
      setDdlLoading(false);
    }
  }, []);

  const handleCopyDdl = useCallback(() => {
    if (!ddl) return;
    navigator.clipboard.writeText(ddl).then(() => {
      setDdlCopied(true);
      setTimeout(() => setDdlCopied(false), 2000);
    });
  }, [ddl]);

  useEffect(() => {
    if (open) {
      setActiveTab("data");
      setOffset(0);
      setData(null);
      setTotalRows(null);
      setError(null);
      setDdl(null);
      setDdlError(null);
      fetchPage(0);
      fetchTotalCount();
    }
  }, [open, tableName, fetchPage, fetchTotalCount]);

  // Lazy-load DDL when switching to schema tab
  useEffect(() => {
    if (open && activeTab === "schema" && ddl === null && !ddlLoading) {
      fetchDdl();
    }
  }, [open, activeTab, ddl, ddlLoading, fetchDdl]);

  const goNext = () => {
    const next = offset + PAGE_SIZE;
    setOffset(next);
    fetchPage(next);
  };

  const goPrev = () => {
    const prev = Math.max(0, offset - PAGE_SIZE);
    setOffset(prev);
    fetchPage(prev);
  };

  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = totalRows != null ? Math.ceil(totalRows / PAGE_SIZE) : null;
  const hasNext = totalRows != null ? offset + PAGE_SIZE < totalRows : (data?.row_count === PAGE_SIZE);
  const hasPrev = offset > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="w-[95vw] max-w-6xl h-[85vh] flex flex-col p-0 bg-card border-border/60 shadow-2xl"
        showCloseButton
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-border/50 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="flex items-center justify-center size-7 rounded-md bg-primary/10 dark:bg-cyan-accent/10">
              <Database className="size-3.5 text-primary dark:text-cyan-accent" />
            </div>
            <DialogTitle className="text-sm font-semibold tracking-wide">
              {datasetName}
            </DialogTitle>
            <Badge variant="secondary" className="text-[10px] font-medium">
              Read-only
            </Badge>
          </div>

          <div className="flex items-center gap-3 mr-8">
            {totalRows != null && activeTab === "data" && (
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Rows3 className="size-3" />
                {totalRows.toLocaleString()} rows
              </span>
            )}
          </div>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 min-h-0 flex flex-col gap-0">
          <div className="px-5 pt-2 shrink-0">
            <TabsList className="h-8">
              <TabsTrigger value="data" className="gap-1.5 text-xs px-3">
                <Rows3 className="size-3.5" />
                Data
              </TabsTrigger>
              <TabsTrigger value="schema" className="gap-1.5 text-xs px-3">
                <Code2 className="size-3.5" />
                Schema
              </TabsTrigger>
            </TabsList>
          </div>

          {/* Data tab */}
          <TabsContent value="data" className="flex-1 min-h-0 flex flex-col">
            <div className="flex-1 min-h-0 overflow-hidden">
              {loading && !data && (
                <div className="flex items-center justify-center h-full gap-2.5 text-muted-foreground">
                  <Loader2 className="size-5 animate-spin text-primary dark:text-cyan-accent" />
                  <span className="text-sm">Loading dataset...</span>
                </div>
              )}

              {error && (
                <div className="mx-5 mt-4 rounded-lg border border-destructive/30 bg-destructive/10 p-3 flex items-start gap-2">
                  <AlertTriangle className="size-4 text-destructive shrink-0 mt-0.5" />
                  <p className="text-sm text-destructive">{error}</p>
                </div>
              )}

              {data && data.columns.length > 0 && (
                <div ref={scrollRef} className="h-full overflow-auto">
                  <DataTable
                    columns={data.columns}
                    rows={data.rows}
                    maxHeight="none"
                    showRowNumbers
                    rowNumberOffset={offset}
                    loading={loading}
                    className="space-y-0"
                    tableClassName="rounded-none border-none"
                    headerRowClassName="bg-secondary dark:bg-accent border-b border-border sticky top-0 z-10"
                    headerCellClassName="py-2.5 text-[11px] font-semibold uppercase tracking-wider text-primary/70 dark:text-cyan-accent/80 bg-inherit"
                    rowClassName={(i) =>
                      i % 2 === 0
                        ? "bg-card hover:bg-accent/50 dark:hover:bg-accent/60 transition-colors"
                        : "bg-muted/30 dark:bg-muted/20 hover:bg-accent/50 dark:hover:bg-accent/60 transition-colors"
                    }
                    cellClassName="border-b border-border/20 text-foreground/85"
                  />
                </div>
              )}

              {data && data.columns.length === 0 && (
                <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                  No data available.
                </div>
              )}
            </div>

            {/* Pagination footer */}
            {data && (
              <div className="flex items-center justify-between px-5 py-2.5 border-t border-border/50 shrink-0 bg-secondary/30 dark:bg-accent/20">
                <span className="text-xs text-muted-foreground tabular-nums">
                  Showing {offset + 1}&ndash;{offset + data.row_count}
                  {totalRows != null && ` of ${totalRows.toLocaleString()}`}
                </span>

                <div className="flex items-center gap-2.5">
                  {totalPages != null && (
                    <span className="text-xs text-muted-foreground tabular-nums">
                      Page {currentPage} of {totalPages}
                    </span>
                  )}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          downloadCsv(
                            data!.columns,
                            data!.rows,
                            `insightxpert-dataset-${tableName}.csv`,
                          )
                        }
                        className="gap-1 h-7 px-2.5 text-xs"
                        aria-label="Download CSV"
                      >
                        <Download className="size-3.5" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">Download CSV</TooltipContent>
                  </Tooltip>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={goPrev}
                    disabled={!hasPrev || loading}
                    className="gap-1 h-7 px-2.5 text-xs"
                  >
                    <ChevronLeft className="size-3.5" />
                    Prev
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={goNext}
                    disabled={!hasNext || loading}
                    className="gap-1 h-7 px-2.5 text-xs"
                  >
                    Next
                    <ChevronRight className="size-3.5" />
                  </Button>
                </div>
              </div>
            )}
          </TabsContent>

          {/* Schema/DDL tab */}
          <TabsContent value="schema" className="flex-1 min-h-0 flex flex-col">
            <div className="flex-1 min-h-0 overflow-auto">
              {ddlLoading && (
                <div className="flex items-center justify-center h-full gap-2.5 text-muted-foreground">
                  <Loader2 className="size-5 animate-spin text-primary dark:text-cyan-accent" />
                  <span className="text-sm">Loading schema...</span>
                </div>
              )}

              {ddlError && (
                <div className="mx-5 mt-4 rounded-lg border border-destructive/30 bg-destructive/10 p-3 flex items-start gap-2">
                  <AlertTriangle className="size-4 text-destructive shrink-0 mt-0.5" />
                  <p className="text-sm text-destructive">{ddlError}</p>
                </div>
              )}

              {ddl && (
                <div className="relative group">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="absolute top-3 right-3 size-7 opacity-0 group-hover:opacity-100 transition-opacity z-10"
                        onClick={handleCopyDdl}
                        aria-label="Copy DDL"
                      >
                        {ddlCopied ? (
                          <Check className="size-3.5 text-green-500" />
                        ) : (
                          <Copy className="size-3.5" />
                        )}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="left">
                      {ddlCopied ? "Copied!" : "Copy DDL"}
                    </TooltipContent>
                  </Tooltip>
                  <pre className="p-5 text-[13px] leading-relaxed font-mono text-foreground/90 whitespace-pre-wrap break-words">
                    <code>{ddl}</code>
                  </pre>
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
