"use client";

import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { PanelLeft, PanelRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/stores/chat-store";
import { useIsMobile } from "@/hooks/use-media-query";
import { Header } from "./header";
import { LeftSidebar } from "./left-sidebar";
import { RightSidebar } from "./right-sidebar";
import {
  Sheet,
  SheetContent,
  SheetTitle,
} from "@/components/ui/sheet";

const sidebarTransition = { duration: 0.2, ease: "easeInOut" } as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const leftOpen = useChatStore((s) => s.leftSidebarOpen);
  const rightOpen = useChatStore((s) => s.rightSidebarOpen);
  const setLeftSidebar = useChatStore((s) => s.setLeftSidebar);
  const setRightSidebar = useChatStore((s) => s.setRightSidebar);
  const toggleLeftSidebar = useChatStore((s) => s.toggleLeftSidebar);
  const toggleRightSidebar = useChatStore((s) => s.toggleRightSidebar);
  const isMobile = useIsMobile();

  // Desktop: both sidebars open by default; Mobile: both collapsed
  useEffect(() => {
    if (isMobile) {
      setLeftSidebar(false);
      setRightSidebar(false);
    } else {
      setLeftSidebar(true);
      setRightSidebar(true);
    }
  }, [isMobile, setLeftSidebar, setRightSidebar]);

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background">
      <Header />

      <div className="flex flex-1 overflow-hidden">
        {isMobile ? (
          <>
            <Sheet open={leftOpen} onOpenChange={setLeftSidebar}>
              <SheetContent side="left" className="w-[85vw] max-w-[320px] p-0" showCloseButton={false}>
                <SheetTitle className="sr-only">Chat History</SheetTitle>
                <LeftSidebar />
              </SheetContent>
            </Sheet>

            <Sheet open={rightOpen} onOpenChange={setRightSidebar}>
              <SheetContent side="right" className="w-[85vw] max-w-[320px] p-0" showCloseButton={false}>
                <SheetTitle className="sr-only">Agent Process</SheetTitle>
                <RightSidebar />
              </SheetContent>
            </Sheet>
          </>
        ) : (
          <AnimatePresence initial={false}>
            {leftOpen && (
              <motion.aside
                key="left-sidebar"
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 280, opacity: 1 }}
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
            <Button
              variant="ghost"
              size="icon"
              className="absolute left-2 top-1/2 -translate-y-1/2 z-10 size-8 opacity-60 hover:opacity-100 transition-opacity"
              onClick={toggleLeftSidebar}
              aria-label="Open chat history"
            >
              <PanelLeft className="size-4" />
            </Button>
          )}

          {/* Floating button to re-open right sidebar when closed */}
          {!isMobile && !rightOpen && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-2 top-1/2 -translate-y-1/2 z-10 size-8 opacity-60 hover:opacity-100 transition-opacity"
              onClick={toggleRightSidebar}
              aria-label="Open agent process"
            >
              <PanelRight className="size-4" />
            </Button>
          )}

          {children}
        </main>

        {!isMobile && (
          <AnimatePresence initial={false}>
            {rightOpen && (
              <motion.aside
                key="right-sidebar"
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 300, opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={sidebarTransition}
                className="shrink-0 overflow-hidden border-l border-border"
              >
                <RightSidebar />
              </motion.aside>
            )}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}
