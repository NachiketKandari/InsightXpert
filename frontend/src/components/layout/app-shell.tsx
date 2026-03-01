"use client";

import React, { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { PanelLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/stores/chat-store";
import { useIsMobile } from "@/hooks/use-media-query";
import { Header } from "./header";
import { LeftSidebar } from "./left-sidebar";
import { SqlExecutor } from "@/components/sql/sql-executor";
import { DatasetViewer } from "@/components/dataset/dataset-viewer";
import { SampleQuestionsModal } from "@/components/sample-questions/sample-questions-modal";
import { WorkflowBuilder } from "@/components/automations/workflow-builder";
import {
  Sheet,
  SheetContent,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";

const sidebarTransition = { duration: 0.2, ease: "easeInOut" } as const;

export const AppShell = React.memo(function AppShell({ children }: { children: React.ReactNode }) {
  const leftOpen = useChatStore((s) => s.leftSidebarOpen);
  const setLeftSidebar = useChatStore((s) => s.setLeftSidebar);
  const toggleLeftSidebar = useChatStore((s) => s.toggleLeftSidebar);
  const sqlExecutorOpen = useChatStore((s) => s.sqlExecutorOpen);
  const setSqlExecutorOpen = useChatStore((s) => s.setSqlExecutorOpen);
  const datasetViewerOpen = useChatStore((s) => s.datasetViewerOpen);
  const setDatasetViewerOpen = useChatStore((s) => s.setDatasetViewerOpen);
  const sampleQuestionsOpen = useChatStore((s) => s.sampleQuestionsOpen);
  const setSampleQuestionsOpen = useChatStore((s) => s.setSampleQuestionsOpen);
  const isMobile = useIsMobile();

  // Desktop: left sidebar open by default; Mobile: collapsed
  useEffect(() => {
    setLeftSidebar(!isMobile);
  }, [isMobile, setLeftSidebar]);

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background">
      <Header />

      <div className="flex flex-1 overflow-hidden">
        {isMobile ? (
          <Sheet open={leftOpen} onOpenChange={setLeftSidebar}>
            <SheetContent side="left" className="w-[85vw] max-w-[320px] p-0" showCloseButton={false}>
              <SheetTitle className="sr-only">Chat History</SheetTitle>
              <LeftSidebar />
            </SheetContent>
          </Sheet>
        ) : (
          <AnimatePresence initial={false}>
            {leftOpen && (
              <motion.aside
                key="left-sidebar"
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 308, opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={sidebarTransition}
                className="shrink-0 overflow-hidden border-r border-border"
              >
                <LeftSidebar />
              </motion.aside>
            )}
          </AnimatePresence>
        )}

        <main className="relative flex-1 min-w-0 overflow-hidden">
          {/* Floating button to re-open left sidebar when closed */}
          {!isMobile && !leftOpen && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute left-2 top-1/2 -translate-y-1/2 z-10 size-8 opacity-60 hover:opacity-100 transition-opacity"
                  onClick={toggleLeftSidebar}
                  aria-label="Open chat history"
                >
                  <PanelLeft className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">Open chat history</TooltipContent>
            </Tooltip>
          )}

          {children}
        </main>

        {/* Desktop: inline SQL executor sidebar */}
        {!isMobile && (
          <AnimatePresence initial={false}>
            {sqlExecutorOpen && (
              <motion.aside
                key="sql-sidebar"
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: "50%", opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={sidebarTransition}
                className="shrink-0 overflow-hidden border-l border-border"
              >
                <SqlExecutor onClose={() => setSqlExecutorOpen(false)} />
              </motion.aside>
            )}
          </AnimatePresence>
        )}
      </div>

      {/* Mobile: SQL Executor as full-screen sheet */}
      {isMobile && (
        <Sheet open={sqlExecutorOpen} onOpenChange={setSqlExecutorOpen}>
          <SheetContent side="right" className="w-full p-0" showCloseButton={false}>
            <SheetTitle className="sr-only">SQL Executor</SheetTitle>
            <SqlExecutor onClose={() => setSqlExecutorOpen(false)} />
          </SheetContent>
        </Sheet>
      )}

      {/* Dataset Viewer modal — triggered from user menu */}
      <DatasetViewer open={datasetViewerOpen} onOpenChange={setDatasetViewerOpen} />

      {/* Sample Questions modal — triggered from user menu */}
      <SampleQuestionsModal open={sampleQuestionsOpen} onOpenChange={setSampleQuestionsOpen} />

      {/* Workflow Builder — triggered from message bubble */}
      <WorkflowBuilder />
    </div>
  );
});
