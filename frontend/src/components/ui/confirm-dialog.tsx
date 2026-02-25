"use client";

import { useCallback, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface ConfirmOptions {
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "destructive" | "default";
}

type ResolverRef = ((confirmed: boolean) => void) | null;

export function useConfirm() {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<ConfirmOptions>({
    title: "",
    description: "",
  });
  const resolverRef = useRef<ResolverRef>(null);

  const confirm = useCallback((opts: ConfirmOptions): Promise<boolean> => {
    setOptions(opts);
    setOpen(true);
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
    });
  }, []);

  const handleClose = useCallback((confirmed: boolean) => {
    setOpen(false);
    resolverRef.current?.(confirmed);
    resolverRef.current = null;
  }, []);

  const ConfirmDialog = useCallback(
    () => (
      <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose(false); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{options.title}</DialogTitle>
            <DialogDescription className="pt-1">
              {options.description}
            </DialogDescription>
          </DialogHeader>
          <div className="flex items-center justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => handleClose(false)}>
              {options.cancelLabel ?? "Cancel"}
            </Button>
            <Button
              variant={options.variant === "default" ? "default" : "destructive"}
              onClick={() => handleClose(true)}
            >
              {options.confirmLabel ?? "Confirm"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    ),
    [open, options, handleClose],
  );

  return { confirm, ConfirmDialog };
}
