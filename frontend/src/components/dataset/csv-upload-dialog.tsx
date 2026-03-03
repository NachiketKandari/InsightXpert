"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import {
  Upload,
  FileSpreadsheet,
  X,
  Loader2,
  ArrowLeft,
  CheckCircle2,
  Rows3,
  Columns3,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { apiFetch } from "@/lib/api";
import { SSE_BASE_URL } from "@/lib/constants";
import { useAuthStore } from "@/stores/auth-store";
import { formatFileName, formatFileSize } from "@/lib/file-utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ColumnProfile {
  name: string;
  original_name: string;
  inferred_type: string;
  distinct_count: number;
  null_count: number;
  null_percent: number;
  is_unique: boolean;
  cardinality: string;
  unique_values: string[] | null;
  min: number | null;
  max: number | null;
  mean: number | null;
}

interface DatasetProfile {
  row_count: number;
  column_count: number;
  columns: ColumnProfile[];
}

interface UploadResult {
  id: string;
  name: string;
  description: string | null;
  ddl: string;
  documentation: string;
  is_active: boolean;
  created_by: string;
  profile: DatasetProfile;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ConfirmedDataset {
  id: string;
  name: string;
  is_active: boolean;
  ddl?: string;
  [key: string]: unknown;
}

interface CsvUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUploadSuccess: (dataset: ConfirmedDataset) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MAX_FILE_SIZE = 500 * 1024 * 1024; // 500 MB — must match server

function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

function humanize(str: string): string {
  return str
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Generate a smart default description for a column based on its profile. */
function defaultDescription(col: ColumnProfile): string {
  if (col.is_unique) return "Unique identifier";
  if (
    (col.inferred_type === "INTEGER" || col.inferred_type === "REAL") &&
    col.min != null &&
    col.max != null
  ) {
    return `Range: ${col.min} - ${col.max}`;
  }
  if (
    col.cardinality === "low" &&
    col.unique_values &&
    col.unique_values.length > 0
  ) {
    const vals = col.unique_values.slice(0, 15).join(", ");
    const suffix = col.unique_values.length > 15 ? ", ..." : "";
    return `Values: ${vals}${suffix}`;
  }
  return humanize(col.name);
}

/** Badge color class per inferred type. */
function typeBadgeClass(type: string): string {
  switch (type) {
    case "TEXT":
      return "border-blue-500/40 text-blue-600 dark:text-blue-400";
    case "INTEGER":
    case "REAL":
      return "border-emerald-500/40 text-emerald-600 dark:text-emerald-400";
    case "BOOLEAN":
      return "border-orange-500/40 text-orange-600 dark:text-orange-400";
    case "DATETIME":
      return "border-purple-500/40 text-purple-600 dark:text-purple-400";
    default:
      return "border-border text-muted-foreground";
  }
}

/** Render column detail summary text. */
function columnDetailText(col: ColumnProfile): string {
  if (col.is_unique) return "Unique identifier";

  if (
    (col.inferred_type === "INTEGER" || col.inferred_type === "REAL") &&
    col.min != null &&
    col.max != null
  ) {
    const avg =
      col.mean != null ? ` (avg: ${Number(col.mean.toFixed(2))})` : "";
    return `Range: ${col.min} \u2013 ${col.max}${avg}`;
  }

  if (
    col.cardinality === "low" &&
    col.unique_values &&
    col.unique_values.length > 0
  ) {
    return col.unique_values.join(", ");
  }

  return `${formatNumber(col.distinct_count)} distinct values`;
}

/** Best-effort DELETE to roll back an unconfirmed upload. */
function rollbackUpload(datasetId: string, token: string | null) {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  // Fire-and-forget — we don't want to block the UI on cleanup
  fetch(`${SSE_BASE_URL}/api/datasets/${datasetId}`, {
    method: "DELETE",
    credentials: "include",
    headers,
  }).catch(() => {});
}

// ---------------------------------------------------------------------------
// Step Components
// ---------------------------------------------------------------------------

type Step = "upload" | "review";

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function CsvUploadDialog({
  open,
  onOpenChange,
  onUploadSuccess,
}: CsvUploadDialogProps) {
  const token = useAuthStore((s) => s.token);

  // Step state
  const [step, setStep] = useState<Step>("upload");
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [columnDescriptions, setColumnDescriptions] = useState<
    Record<string, string>
  >({});
  const [confirming, setConfirming] = useState(false);

  // Upload form state
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  // Tracks what the server is doing after bytes are fully sent
  const [uploadPhase, setUploadPhase] = useState<
    "sending" | "processing" | null
  >(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const xhrRef = useRef<XMLHttpRequest | null>(null);

  // Track whether confirm has been completed (to avoid rollback after confirm)
  const confirmedRef = useRef(false);

  const reset = useCallback(() => {
    setStep("upload");
    setUploadResult(null);
    setColumnDescriptions({});
    setConfirming(false);
    setFile(null);
    setName("");
    setDescription("");
    setError(null);
    setUploading(false);
    setUploadProgress(0);
    setUploadPhase(null);
    confirmedRef.current = false;
    if (xhrRef.current) {
      xhrRef.current.abort();
      xhrRef.current = null;
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  // Roll back unconfirmed upload when closing the dialog on the review step
  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen && uploadResult && !confirmedRef.current) {
        rollbackUpload(uploadResult.id, token);
      }
      if (!nextOpen) reset();
      onOpenChange(nextOpen);
    },
    [uploadResult, token, reset, onOpenChange],
  );

  // Cancel in-flight XHR on unmount
  useEffect(() => {
    return () => {
      if (xhrRef.current) {
        xhrRef.current.abort();
        xhrRef.current = null;
      }
    };
  }, []);

  // Best-effort cleanup on browser close / navigation
  useEffect(() => {
    if (step !== "review" || !uploadResult || confirmedRef.current) return;

    const id = uploadResult.id;
    const handleBeforeUnload = () => {
      rollbackUpload(id, token);
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [step, uploadResult, token]);

  // ---- Upload step handlers ----

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (!selected) return;

    if (!selected.name.toLowerCase().endsWith(".csv")) {
      setError("Please select a CSV file.");
      return;
    }

    if (selected.size > MAX_FILE_SIZE) {
      setError(
        `File is too large (${formatFileSize(selected.size)}). Maximum is ${formatFileSize(MAX_FILE_SIZE)}.`,
      );
      return;
    }

    setFile(selected);
    setError(null);

    // Auto-fill name from file name if empty
    if (!name.trim()) {
      setName(formatFileName(selected.name));
    }
  };

  const handleRemoveFile = () => {
    setFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleUpload = async (
    e: React.FormEvent<HTMLFormElement> | React.MouseEvent<HTMLButtonElement>,
  ) => {
    e.preventDefault();

    if (!file) {
      setError("Please select a CSV file.");
      return;
    }
    if (!name.trim()) {
      setError("Please enter a dataset name.");
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    setUploadPhase("sending");
    setError(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("name", name.trim());
    if (description.trim()) {
      formData.append("description", description.trim());
    }

    // Use XHR for upload progress tracking.
    // Send directly to SSE_BASE_URL (bypasses Next.js proxy body size limit)
    // with Bearer token auth (same pattern as SSE streaming).
    const xhr = new XMLHttpRequest();
    xhrRef.current = xhr;

    xhr.upload.onprogress = (evt) => {
      if (evt.lengthComputable) {
        const pct = Math.round((evt.loaded / evt.total) * 100);
        setUploadProgress(pct);
        if (pct >= 100) {
          setUploadPhase("processing");
        }
      }
    };

    // All bytes sent — server is now working
    xhr.upload.onload = () => {
      setUploadPhase("processing");
    };

    xhr.onload = () => {
      xhrRef.current = null;
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data: UploadResult = JSON.parse(xhr.responseText);
          setUploadResult(data);

          // Initialize descriptions with smart defaults
          const descs: Record<string, string> = {};
          for (const col of data.profile.columns) {
            descs[col.name] = defaultDescription(col);
          }
          setColumnDescriptions(descs);

          setStep("review");
        } catch {
          setError("Invalid response from server.");
        }
      } else {
        try {
          const body = JSON.parse(xhr.responseText);
          setError(body.detail || `Upload failed (HTTP ${xhr.status})`);
        } catch {
          setError(`Upload failed (HTTP ${xhr.status})`);
        }
      }
      setUploading(false);
      setUploadPhase(null);
    };

    xhr.onerror = () => {
      xhrRef.current = null;
      setError("Network error during upload.");
      setUploading(false);
      setUploadPhase(null);
    };

    xhr.onabort = () => {
      xhrRef.current = null;
      setUploading(false);
      setUploadPhase(null);
    };

    xhr.open("POST", `${SSE_BASE_URL}/api/datasets/upload`);
    xhr.withCredentials = true;
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }
    xhr.send(formData);
  };

  // ---- Review step handlers ----

  const handleDescriptionChange = (colName: string, value: string) => {
    setColumnDescriptions((prev) => ({ ...prev, [colName]: value }));
  };

  const handleBack = () => {
    // Roll back the unconfirmed upload before going back
    if (uploadResult && !confirmedRef.current) {
      rollbackUpload(uploadResult.id, token);
    }
    setStep("upload");
    setUploadResult(null);
    setError(null);
  };

  const handleConfirm = async () => {
    if (!uploadResult) return;

    setConfirming(true);
    setError(null);

    try {
      const res = await apiFetch(
        `/api/datasets/${uploadResult.id}/confirm`,
        {
          method: "POST",
          body: JSON.stringify({
            column_descriptions: columnDescriptions,
            profile: uploadResult.profile,
          }),
        },
      );

      if (!res.ok) {
        const body = await res
          .json()
          .catch(() => ({ detail: `Confirm failed (HTTP ${res.status})` }));
        setError(body.detail || `Confirm failed (HTTP ${res.status})`);
        setConfirming(false);
        return;
      }

      confirmedRef.current = true;

      const confirmed: ConfirmedDataset = await res.json();
      toast.success("Dataset confirmed and ready to query");

      // Notify all listeners (e.g. the navbar DatasetSelector) regardless
      // of which component tree rendered this dialog.
      window.dispatchEvent(
        new CustomEvent("dataset-changed", { detail: confirmed }),
      );

      onUploadSuccess(confirmed);
      handleOpenChange(false);
    } catch (err) {
      setError((err as Error).message || "Network error during confirmation.");
    } finally {
      setConfirming(false);
    }
  };

  // ---- Render ----

  const isReview = step === "review" && uploadResult != null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className={
          isReview
            ? "sm:max-w-4xl w-full max-h-[90vh] flex flex-col overflow-hidden p-0"
            : "sm:max-w-md"
        }
      >
        {/* ---------- STEP 1: Upload ---------- */}
        {step === "upload" && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 text-sm">
                <Upload className="size-4 text-primary dark:text-cyan-accent" />
                Upload CSV Dataset
              </DialogTitle>
              <DialogDescription>
                Upload a CSV file to create a new queryable dataset.
              </DialogDescription>
            </DialogHeader>

            <form onSubmit={handleUpload} className="space-y-4 px-4">
              {/* File picker */}
              <div className="space-y-2">
                <Label htmlFor="csv-file" className="text-xs font-medium">
                  CSV File
                </Label>
                {!file ? (
                  <div
                    className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border/60 bg-muted/30 p-6 cursor-pointer hover:border-primary/40 hover:bg-muted/50 transition-colors"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <FileSpreadsheet className="size-8 text-muted-foreground/60" />
                    <p className="text-sm text-muted-foreground">
                      Click to select a CSV file
                    </p>
                    <p className="text-xs text-muted-foreground/60">
                      .csv files up to {formatFileSize(MAX_FILE_SIZE)}
                    </p>
                  </div>
                ) : (
                  <div className="flex items-center gap-3 rounded-lg border border-border/60 bg-muted/30 p-3">
                    <FileSpreadsheet className="size-5 text-primary dark:text-cyan-accent shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {file.name}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatFileSize(file.size)}
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-7 shrink-0"
                      onClick={handleRemoveFile}
                      aria-label="Remove file"
                    >
                      <X className="size-3.5" />
                    </Button>
                  </div>
                )}
                <input
                  ref={fileInputRef}
                  id="csv-file"
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={handleFileChange}
                />
              </div>

              {/* Dataset name */}
              <div className="space-y-2">
                <Label htmlFor="dataset-name" className="text-xs font-medium">
                  Dataset Name <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="dataset-name"
                  placeholder="e.g. Q4 Sales Transactions"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={uploading}
                />
              </div>

              {/* Description */}
              <div className="space-y-2">
                <Label
                  htmlFor="dataset-description"
                  className="text-xs font-medium"
                >
                  Description{" "}
                  <span className="text-muted-foreground">(optional)</span>
                </Label>
                <Textarea
                  id="dataset-description"
                  placeholder="Brief description of the dataset..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={uploading}
                  rows={2}
                />
              </div>

              {/* Error message */}
              {error && <p className="text-sm text-destructive">{error}</p>}

              {/* Upload progress indicator */}
              {uploading && (
                <div className="space-y-2">
                  <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                    {uploadPhase === "processing" ? (
                      <div className="h-full bg-primary dark:bg-cyan-accent rounded-full animate-pulse w-full" />
                    ) : (
                      <div
                        className="h-full bg-primary dark:bg-cyan-accent rounded-full transition-all duration-300"
                        style={{ width: `${uploadProgress}%` }}
                      />
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground text-center">
                    {uploadPhase === "processing"
                      ? "File uploaded. Analyzing schema, loading data, and profiling columns..."
                      : uploadProgress > 0
                        ? `Sending file... ${uploadProgress}%`
                        : "Starting upload..."}
                  </p>
                </div>
              )}
            </form>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => handleOpenChange(false)}
                disabled={uploading}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                size="sm"
                disabled={uploading || !file || !name.trim()}
                onClick={handleUpload}
              >
                {uploading ? (
                  <>
                    <Loader2 className="size-3.5 animate-spin mr-1.5" />
                    {uploadPhase === "processing"
                      ? "Processing data..."
                      : `Uploading${uploadProgress > 0 ? ` ${uploadProgress}%` : "..."}`}
                  </>
                ) : (
                  <>
                    <Upload className="size-3.5 mr-1.5" />
                    Upload
                  </>
                )}
              </Button>
            </DialogFooter>
          </>
        )}

        {/* ---------- STEP 2: Profile Review ---------- */}
        {isReview && (
          <>
            {/* Fixed header */}
            <div className="shrink-0 flex flex-col gap-1.5 p-4 pb-0">
              <DialogTitle className="flex items-center gap-2 text-sm">
                <CheckCircle2 className="size-4 text-primary dark:text-cyan-accent" />
                Review Dataset Profile
              </DialogTitle>
              <DialogDescription>
                We analyzed your data. Review column details and descriptions,
                then confirm.
              </DialogDescription>

              {/* Summary bar */}
              <div className="flex items-center gap-3 pt-2">
                <div className="flex items-center gap-1.5 rounded-md border border-border/60 bg-muted/30 px-2.5 py-1.5">
                  <Rows3 className="size-3.5 text-primary dark:text-cyan-accent" />
                  <span className="text-xs font-medium">
                    {formatNumber(uploadResult.profile.row_count)} rows
                  </span>
                </div>
                <div className="flex items-center gap-1.5 rounded-md border border-border/60 bg-muted/30 px-2.5 py-1.5">
                  <Columns3 className="size-3.5 text-primary dark:text-cyan-accent" />
                  <span className="text-xs font-medium">
                    {formatNumber(uploadResult.profile.column_count)} columns
                  </span>
                </div>
                {uploadResult.name && (
                  <span className="ml-auto text-xs text-muted-foreground truncate max-w-[200px]">
                    {uploadResult.name}
                  </span>
                )}
              </div>
            </div>

            {/* Scrollable column table */}
            <div className="flex-1 min-h-0 overflow-y-auto mx-4 rounded-md border border-border/60">
              {/* Sticky table header */}
              <div className="sticky top-0 z-10 grid grid-cols-[140px_72px_70px_1fr_1fr] gap-2 border-b border-border/60 bg-muted px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                <span>Column</span>
                <span>Type</span>
                <span>Distinct</span>
                <span>Details</span>
                <span>Description</span>
              </div>

              {/* Column rows */}
              <div className="divide-y divide-border/40">
                {uploadResult.profile.columns.map((col) => (
                  <div
                    key={col.name}
                    className="grid grid-cols-[140px_72px_70px_1fr_1fr] gap-2 items-start px-3 py-2 hover:bg-muted/20 transition-colors"
                  >
                    {/* Column name */}
                    <div className="min-w-0">
                      <span className="font-mono text-xs font-medium truncate block">
                        {col.name}
                      </span>
                      {col.null_percent > 0 && (
                        <span className="text-[10px] text-muted-foreground/70">
                          {col.null_percent.toFixed(1)}% null
                        </span>
                      )}
                    </div>

                    {/* Type badge */}
                    <div>
                      <Badge
                        variant="outline"
                        className={`text-[10px] px-1.5 py-0 font-mono ${typeBadgeClass(col.inferred_type)}`}
                      >
                        {col.inferred_type}
                      </Badge>
                    </div>

                    {/* Distinct count */}
                    <div className="text-xs text-muted-foreground tabular-nums">
                      {formatNumber(col.distinct_count)}
                      {col.is_unique && (
                        <span className="block text-[10px] text-primary dark:text-cyan-accent">
                          unique
                        </span>
                      )}
                    </div>

                    {/* Details */}
                    <div className="min-w-0">
                      {col.cardinality === "low" &&
                      col.unique_values &&
                      col.unique_values.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {col.unique_values.slice(0, 8).map((v) => (
                            <span
                              key={v}
                              className="inline-block rounded bg-muted/60 border border-border/40 px-1.5 py-px text-[10px] text-muted-foreground truncate max-w-[100px]"
                            >
                              {v}
                            </span>
                          ))}
                          {col.unique_values.length > 8 && (
                            <span className="text-[10px] text-muted-foreground/60 self-center">
                              +{col.unique_values.length - 8} more
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground leading-snug line-clamp-2">
                          {columnDetailText(col)}
                        </span>
                      )}
                    </div>

                    {/* Editable description */}
                    <div>
                      <Input
                        className="h-7 text-xs px-2"
                        value={columnDescriptions[col.name] ?? ""}
                        onChange={(e) =>
                          handleDescriptionChange(col.name, e.target.value)
                        }
                        placeholder="Describe this column..."
                        disabled={confirming}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Error message */}
            {error && <p className="text-sm text-destructive px-4">{error}</p>}

            {/* Fixed footer */}
            <div className="shrink-0 flex items-center justify-end gap-2 p-4">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleBack}
                disabled={confirming}
              >
                <ArrowLeft className="size-3.5 mr-1.5" />
                Back
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={confirming}
                onClick={handleConfirm}
              >
                {confirming ? (
                  <>
                    <Loader2 className="size-3.5 animate-spin mr-1.5" />
                    Confirming...
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="size-3.5 mr-1.5" />
                    Confirm
                  </>
                )}
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
