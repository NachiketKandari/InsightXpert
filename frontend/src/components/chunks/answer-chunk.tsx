"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface AnswerChunkProps {
  content: string;
}

function AnswerChunkInner({ content }: AnswerChunkProps) {
  return (
    <div className="prose-invert prose-sm max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-lg font-bold text-foreground mt-4 mb-2">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-base font-semibold text-foreground mt-3 mb-2">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-semibold text-foreground mt-2 mb-1">
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="text-sm text-foreground/90 leading-relaxed mb-2">
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul className="text-sm text-foreground/90 list-disc list-inside space-y-1 mb-2">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="text-sm text-foreground/90 list-decimal list-inside space-y-1 mb-2">
              {children}
            </ol>
          ),
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          strong: ({ children }) => (
            <strong className="font-semibold text-foreground">{children}</strong>
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
            <pre className="bg-muted rounded-lg overflow-x-auto my-2">
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto my-2 rounded-lg border border-border">
              <table className="w-full text-sm">{children}</table>
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
            <td className="px-3 py-1.5 text-xs font-mono border-t border-border">
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
            <blockquote className="border-l-2 border-primary/50 pl-3 text-sm text-muted-foreground italic my-2">
              {children}
            </blockquote>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

// Memoized to prevent React-Markdown re-parsing on every parent re-render
// when the content string hasn't changed (e.g. sibling chunks updating).
export const AnswerChunk = React.memo(AnswerChunkInner);
