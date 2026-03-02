"use client";

import { useState, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BookOpen, FileText, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

interface DocEntry {
  label: string;
  path: string;
}

interface DocGroup {
  title: string;
  docs: DocEntry[];
}

const DOC_GROUPS: DocGroup[] = [
  {
    title: "Overview",
    docs: [
      { label: "README", path: "/docs/README.md" },
      { label: "Architecture", path: "/docs/ARCHITECTURE.md" },
      { label: "Walkthrough", path: "/docs/WALKTHROUGH.md" },
      { label: "Design Patterns", path: "/docs/DESIGN_PATTERNS.md" },
    ],
  },
  {
    title: "Guides",
    docs: [
      { label: "Agent Pipeline", path: "/docs/guides/agent-pipeline.md" },
      { label: "Agent Tools", path: "/docs/guides/agent-tools.md" },
      { label: "Agents & Modes", path: "/docs/guides/AGENTS_AND_MODES.md" },
      { label: "API Reference", path: "/docs/guides/api-reference.md" },
      { label: "Architecture (Detail)", path: "/docs/guides/architecture.md" },
      { label: "Automations", path: "/docs/guides/automations.md" },
      { label: "Configuration", path: "/docs/guides/configuration.md" },
      { label: "Contributing", path: "/docs/guides/contributing.md" },
      { label: "Dataset", path: "/docs/guides/dataset.md" },
      { label: "Frontend", path: "/docs/guides/frontend.md" },
    ],
  },
];

export function DocsDialog() {
  const [open, setOpen] = useState(false);
  const [activePath, setActivePath] = useState(DOC_GROUPS[0].docs[0].path);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);

  const fetchDoc = useCallback(async (path: string) => {
    setLoading(true);
    try {
      const res = await fetch(path);
      if (!res.ok) throw new Error("Failed to load");
      const text = await res.text();
      setContent(text);
    } catch {
      setContent("Failed to load document.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      fetchDoc(activePath);
    }
  }, [open, activePath, fetchDoc]);

  const activeLabel =
    DOC_GROUPS.flatMap((g) => g.docs).find((d) => d.path === activePath)
      ?.label ?? "";

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Tooltip>
        <TooltipTrigger asChild>
          <DialogTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-9"
              aria-label="Documentation"
            >
              <BookOpen className="size-5" />
            </Button>
          </DialogTrigger>
        </TooltipTrigger>
        <TooltipContent side="bottom">Documentation</TooltipContent>
      </Tooltip>

      <DialogContent
        showCloseButton
        className="w-[95vw] max-w-5xl h-[80vh] flex flex-col p-0 gap-0"
      >
        <DialogHeader className="border-b border-border px-4 py-3 shrink-0">
          <DialogTitle className="flex items-center gap-2 text-base">
            <BookOpen className="size-4" />
            Documentation
          </DialogTitle>
          <DialogDescription className="sr-only">
            Browse project documentation
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-1 min-h-0">
          {/* Sidebar */}
          <ScrollArea className="w-56 shrink-0 border-r border-border">
            <nav className="p-2 space-y-3">
              {DOC_GROUPS.map((group) => (
                <div key={group.title}>
                  <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground px-2 mb-1">
                    {group.title}
                  </h4>
                  <ul className="space-y-0.5">
                    {group.docs.map((doc) => (
                      <li key={doc.path}>
                        <button
                          onClick={() => setActivePath(doc.path)}
                          className={cn(
                            "flex items-center gap-1.5 w-full text-left text-sm px-2 py-1.5 rounded-md transition-colors",
                            activePath === doc.path
                              ? "bg-primary/10 text-primary font-medium"
                              : "text-muted-foreground hover:text-foreground hover:bg-muted"
                          )}
                        >
                          <FileText className="size-3.5 shrink-0" />
                          <span className="truncate">{doc.label}</span>
                          {activePath === doc.path && (
                            <ChevronRight className="size-3 ml-auto shrink-0" />
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </nav>
          </ScrollArea>

          {/* Content */}
          <ScrollArea className="flex-1 min-w-0">
            <div className="p-6 max-w-3xl">
              {loading ? (
                <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
                  Loading {activeLabel}...
                </div>
              ) : (
                <article className="prose-invert prose-sm max-w-none">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      h1: ({ children }) => (
                        <h1 className="text-2xl font-bold text-foreground mt-6 mb-3 first:mt-0">
                          {children}
                        </h1>
                      ),
                      h2: ({ children }) => (
                        <h2 className="text-xl font-semibold text-foreground mt-5 mb-2">
                          {children}
                        </h2>
                      ),
                      h3: ({ children }) => (
                        <h3 className="text-base font-semibold text-foreground mt-4 mb-1.5">
                          {children}
                        </h3>
                      ),
                      h4: ({ children }) => (
                        <h4 className="text-sm font-semibold text-foreground mt-3 mb-1">
                          {children}
                        </h4>
                      ),
                      p: ({ children }) => (
                        <p className="text-sm text-foreground/90 leading-relaxed mb-3">
                          {children}
                        </p>
                      ),
                      ul: ({ children }) => (
                        <ul className="text-sm text-foreground/90 list-disc list-outside pl-5 space-y-1 mb-3">
                          {children}
                        </ul>
                      ),
                      ol: ({ children }) => (
                        <ol className="text-sm text-foreground/90 list-decimal list-outside pl-5 space-y-1 mb-3">
                          {children}
                        </ol>
                      ),
                      li: ({ children }) => (
                        <li className="leading-relaxed">{children}</li>
                      ),
                      strong: ({ children }) => (
                        <strong className="font-semibold text-foreground">
                          {children}
                        </strong>
                      ),
                      code: ({ children, className }) => {
                        const isInline = !className;
                        if (isInline) {
                          return (
                            <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono text-primary">
                              {children}
                            </code>
                          );
                        }
                        return (
                          <code className="block bg-muted p-3 rounded-lg text-xs font-mono overflow-x-auto my-2">
                            {children}
                          </code>
                        );
                      },
                      pre: ({ children }) => (
                        <pre className="bg-muted rounded-lg overflow-x-auto my-3">
                          {children}
                        </pre>
                      ),
                      table: ({ children }) => (
                        <div className="overflow-x-auto my-3 rounded-lg border border-border">
                          <table className="w-full text-sm">
                            {children}
                          </table>
                        </div>
                      ),
                      thead: ({ children }) => (
                        <thead className="bg-muted/50">{children}</thead>
                      ),
                      th: ({ children }) => (
                        <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">
                          {children}
                        </th>
                      ),
                      td: ({ children }) => (
                        <td className="px-3 py-1.5 text-xs border-t border-border">
                          {children}
                        </td>
                      ),
                      a: ({ children, href }) => (
                        <a
                          href={href}
                          className="text-primary underline underline-offset-2 hover:text-primary/80"
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {children}
                        </a>
                      ),
                      blockquote: ({ children }) => (
                        <blockquote className="border-l-2 border-primary/50 pl-3 text-sm text-muted-foreground italic my-3">
                          {children}
                        </blockquote>
                      ),
                      hr: () => (
                        <hr className="border-border my-4" />
                      ),
                    }}
                  >
                    {content}
                  </ReactMarkdown>
                </article>
              )}
            </div>
          </ScrollArea>
        </div>
      </DialogContent>
    </Dialog>
  );
}
