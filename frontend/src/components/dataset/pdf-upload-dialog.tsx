"use client";

import { useState, useRef, useCallback } from "react";
import {
  Upload,
  FileText,
  X,
  Loader2,
  CheckCircle2,
  BookOpen,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { apiFetch } from "@/lib/api";
import { formatFileName, formatFileSize } from "@/lib/file-utils";

interface UploadResult {
  id: string;
  name: string;
  description: string | null;
  file_name: string;
  page_count: number;
  extracted_text_preview: string | null;
}

interface PdfUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUploadSuccess: () => void;
}

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20 MB

export function PdfUploadDialog({
  open,
  onOpenChange,
  onUploadSuccess,
}: PdfUploadDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const reset = useCallback(() => {
    setFile(null);
    setName("");
    setDescription("");
    setError(null);
    setUploading(false);
    setResult(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) reset();
    onOpenChange(nextOpen);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (!selected) return;
    if (!selected.name.toLowerCase().endsWith(".pdf")) {
      setError("Please select a PDF file.");
      return;
    }
    if (selected.size > MAX_FILE_SIZE) {
      setError(`File is too large (${formatFileSize(selected.size)}). Maximum is ${formatFileSize(MAX_FILE_SIZE)}.`);
      return;
    }
    setFile(selected);
    setError(null);
    if (!name.trim()) setName(formatFileName(selected.name));
  };

  const handleRemoveFile = () => {
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleUpload = async (e: React.FormEvent | React.MouseEvent) => {
    e.preventDefault();
    if (!file) { setError("Please select a PDF file."); return; }
    if (!name.trim()) { setError("Please enter a document name."); return; }

    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("name", name.trim());
      if (description.trim()) formData.append("description", description.trim());

      const res = await apiFetch("/api/documents/upload", { method: "POST", body: formData });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: `Upload failed (HTTP ${res.status})` }));
        setError(body.detail || `Upload failed (HTTP ${res.status})`);
        setUploading(false);
        return;
      }

      const data: UploadResult = await res.json();
      setResult(data);
      toast.success(`Document uploaded (${data.page_count} pages)`);
    } catch (err) {
      setError((err as Error).message || "Network error during upload.");
    } finally {
      setUploading(false);
    }
  };

  const handleDone = () => {
    handleOpenChange(false);
    onUploadSuccess();
  };

  // Result view after successful upload
  if (result) {
    return (
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="sm:max-w-lg w-[calc(100vw-2rem)] max-h-[85vh] overflow-y-auto overflow-x-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-sm">
              <CheckCircle2 className="size-4 text-emerald-500" />
              Document Uploaded
            </DialogTitle>
            <DialogDescription>
              Successfully extracted text from {result.page_count} page{result.page_count !== 1 ? "s" : ""}.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 px-4">
            <div className="flex items-center gap-2">
              <BookOpen className="size-4 text-primary" />
              <span className="text-sm font-medium">{result.name}</span>
              <span className="text-xs text-muted-foreground">({result.file_name})</span>
            </div>
            {result.extracted_text_preview && (
              <ScrollArea className="max-h-[200px] rounded-md border border-border/60 p-3">
                <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">
                  {result.extracted_text_preview}
                </p>
              </ScrollArea>
            )}
          </div>
          <DialogFooter>
            <Button size="sm" onClick={handleDone}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  // Upload form
  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg w-[calc(100vw-2rem)] max-h-[85vh] overflow-y-auto overflow-x-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <FileText className="size-4 text-primary dark:text-cyan-accent" />
            Upload Document
          </DialogTitle>
          <DialogDescription>
            Upload a PDF document to use as context for analysis.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleUpload} className="space-y-4 px-4">
          <div className="space-y-2">
            <Label htmlFor="pdf-file" className="text-xs font-medium">PDF File</Label>
            {!file ? (
              <div
                className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border/60 bg-muted/30 p-6 cursor-pointer hover:border-primary/40 hover:bg-muted/50 transition-colors"
                onClick={() => fileInputRef.current?.click()}
              >
                <FileText className="size-8 text-muted-foreground/60" />
                <p className="text-sm text-muted-foreground">Click to select a PDF file</p>
                <p className="text-xs text-muted-foreground/60">.pdf files only, max {formatFileSize(MAX_FILE_SIZE)}</p>
              </div>
            ) : (
              <div className="flex items-center gap-3 rounded-lg border border-border/60 bg-muted/30 p-3">
                <FileText className="size-5 text-primary dark:text-cyan-accent shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{file.name}</p>
                  <p className="text-xs text-muted-foreground">{formatFileSize(file.size)}</p>
                </div>
                <Button type="button" variant="ghost" size="icon" className="size-7 shrink-0" onClick={handleRemoveFile} aria-label="Remove file">
                  <X className="size-3.5" />
                </Button>
              </div>
            )}
            <input ref={fileInputRef} id="pdf-file" type="file" accept=".pdf" className="hidden" onChange={handleFileChange} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="doc-name" className="text-xs font-medium">Document Name <span className="text-destructive">*</span></Label>
            <Input id="doc-name" placeholder="e.g. Q4 Financial Report" value={name} onChange={(e) => setName(e.target.value)} disabled={uploading} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="doc-description" className="text-xs font-medium">Description <span className="text-muted-foreground">(optional)</span></Label>
            <Textarea id="doc-description" placeholder="Brief description of the document..." value={description} onChange={(e) => setDescription(e.target.value)} disabled={uploading} rows={2} />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </form>
        <DialogFooter>
          <Button type="button" variant="outline" size="sm" onClick={() => handleOpenChange(false)} disabled={uploading}>Cancel</Button>
          <Button type="submit" size="sm" disabled={uploading || !file || !name.trim()} onClick={handleUpload}>
            {uploading ? (<><Loader2 className="size-3.5 animate-spin mr-1.5" />Uploading...</>) : (<><Upload className="size-3.5 mr-1.5" />Upload</>)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
