import type { Message, Conversation, EnrichmentTrace } from "@/types/chat";

// ---------------------------------------------------------------------------
// Lightweight markdown → HTML conversion (covers the patterns used by the
// InsightXpert response generator: headings, bold, italic, lists, code
// blocks, inline code, tables, blockquotes, citations).
// ---------------------------------------------------------------------------

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function markdownToHtml(md: string): string {
  // Escape HTML first to prevent XSS, then apply markdown transforms
  // on the escaped string. Code blocks are handled specially.
  let html = md;

  // Extract and escape fenced code blocks before global escape
  const codeBlocks: string[] = [];
  html = html.replace(/```[\w]*\n([\s\S]*?)```/g, (_m, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push(`<pre><code>${escapeHtml(code.trimEnd())}</code></pre>`);
    return `\x00CB${idx}\x00`;
  });

  // Escape remaining HTML entities
  html = escapeHtml(html);

  // Restore code blocks
  html = html.replace(/\x00CB(\d+)\x00/g, (_m, idx) => codeBlocks[Number(idx)]);

  // GFM tables ─ header | sep | body rows (already escaped)
  html = html.replace(
    /^(\|.+\|)\n(\|[\s\-:|]+\|)\n((?:\|.+\|\n?)*)/gm,
    (_m, headerLine: string, _sep: string, bodyBlock: string) => {
      const headers = headerLine
        .split("|")
        .map((h: string) => h.trim())
        .filter(Boolean);
      const rows = bodyBlock
        .trim()
        .split("\n")
        .map((row: string) =>
          row
            .split("|")
            .map((c: string) => c.trim())
            .filter(Boolean),
        );
      let t = "<table><thead><tr>";
      for (const h of headers) t += `<th>${h}</th>`;
      t += "</tr></thead><tbody>";
      for (const row of rows) {
        t += "<tr>";
        for (const cell of row) t += `<td>${cell}</td>`;
        t += "</tr>";
      }
      t += "</tbody></table>";
      return t;
    },
  );

  // Headers (content already escaped)
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

  // Bold + italic (** and * were escaped as-is since they're not HTML)
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code class='inline'>$1</code>");

  // Ordered lists — process BEFORE unordered to avoid <ul> wrapping
  html = html.replace(/^\d+\.\s+(.+)$/gm, "<oli>$1</oli>");
  html = html.replace(/((?:<oli>.*<\/oli>\n?)+)/g, (m) =>
    "<ol>" + m.replace(/<\/?oli>/g, (tag) => tag.replace("oli", "li")) + "</ol>",
  );

  // Unordered lists — group consecutive `- ` lines
  html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

  // Blockquotes
  html = html.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");

  // Citations [[N]] → superscript
  html = html.replace(/\[\[(\d+)\]\]/g, '<sup class="citation">[$1]</sup>');

  // Paragraphs: double newline → paragraph break
  html = html.replace(/\n{2,}/g, "</p><p>");
  html = "<p>" + html + "</p>";

  // Clean up paragraphs wrapping block elements
  const blocks = "h[1-6]|ul|ol|pre|blockquote|table";
  html = html.replace(new RegExp(`<p>\\s*(<(?:${blocks})>)`, "g"), "$1");
  html = html.replace(new RegExp(`(</(?:${blocks})>)\\s*</p>`, "g"), "$1");
  html = html.replace(/<p>\s*<\/p>/g, "");

  return html;
}

// ---------------------------------------------------------------------------
// Extract structured data from message chunks
// ---------------------------------------------------------------------------

interface ReportData {
  sqls: string[];
  enrichmentTraces: EnrichmentTrace[];
  answer: string;
  insight: string;
  inputTokens?: number | null;
  outputTokens?: number | null;
  generationTimeMs?: number | null;
}

function extractReportData(message: Message): ReportData {
  const sqls: string[] = [];
  const enrichmentTraces: EnrichmentTrace[] = [];
  let answer = "";
  let insight = "";

  for (const chunk of message.chunks) {
    if (chunk.type === "sql" && chunk.sql) sqls.push(chunk.sql);
    if (chunk.type === "enrichment_trace" && chunk.data)
      enrichmentTraces.push(chunk.data as unknown as EnrichmentTrace);
    if (chunk.type === "answer" && chunk.content) answer = chunk.content;
    if (chunk.type === "insight" && chunk.content) insight = chunk.content;
  }

  return {
    sqls,
    enrichmentTraces,
    answer,
    insight,
    inputTokens: message.inputTokens,
    outputTokens: message.outputTokens,
    generationTimeMs: message.generationTimeMs ?? message.wallTimeMs,
  };
}

// ---------------------------------------------------------------------------
// HTML report template
// ---------------------------------------------------------------------------

const REPORT_CSS = `
@page { margin: 2cm; size: A4; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
  line-height: 1.7;
  color: #1a1a2e;
  max-width: 780px;
  margin: 0 auto;
  padding: 32px 24px;
  background: #fff;
}
.header { border-bottom: 2px solid #1a1a2e; padding-bottom: 12px; margin-bottom: 24px; }
.header h1 { font-size: 22px; margin: 0 0 4px; }
.header .meta { font-size: 12px; color: #666; }
.question-block {
  background: #f0f4ff;
  border-left: 4px solid #3b5bdb;
  padding: 12px 16px;
  margin: 20px 0;
  border-radius: 0 6px 6px 0;
}
.question-block .label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #3b5bdb; font-weight: 600; margin-bottom: 4px; }
.question-block .text { font-size: 15px; color: #1a1a2e; }
.response h2 { font-size: 16px; color: #1a1a2e; border-bottom: 1px solid #e0e0e0; padding-bottom: 4px; margin-top: 28px; }
.response h3 { font-size: 14px; color: #333; margin-top: 20px; }
.response p { font-size: 13px; margin: 8px 0; }
.response ul, .response ol { font-size: 13px; padding-left: 24px; }
.response li { margin: 4px 0; }
.response strong { color: #1a1a2e; }
.response table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 12px; }
.response th, .response td { border: 1px solid #d0d0d0; padding: 6px 10px; text-align: left; }
.response th { background: #f5f5f5; font-weight: 600; }
.response pre { background: #f5f5f5; padding: 12px; border-radius: 4px; font-size: 11px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; }
.response code.inline { background: #f0f0f0; padding: 1px 5px; border-radius: 3px; font-size: 12px; font-family: 'SFMono-Regular', Consolas, monospace; }
.response blockquote { border-left: 3px solid #3b5bdb; padding-left: 12px; color: #555; font-style: italic; margin: 12px 0; }
.citation { color: #3b5bdb; font-size: 10px; vertical-align: super; }
.sql-section { margin-top: 24px; }
.sql-section h3 { font-size: 13px; color: #666; }
.sql-section pre { background: #1a1a2e; color: #e0e0e0; padding: 12px; border-radius: 6px; font-size: 11px; }
.traces { margin-top: 24px; page-break-inside: avoid; }
.trace-card { border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px; margin: 8px 0; }
.trace-card .cat { font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #3b5bdb; font-weight: 600; }
.trace-card .q { font-size: 13px; font-weight: 500; margin: 4px 0 8px; }
.trace-card .ans { font-size: 12px; color: #444; }
.metrics { margin-top: 20px; padding: 10px 16px; background: #fafafa; border-radius: 6px; font-size: 12px; color: #666; }
.divider { border-top: 1px solid #e0e0e0; margin: 28px 0; }
.message-pair { page-break-inside: avoid; margin-bottom: 28px; }
.footer { margin-top: 32px; padding-top: 12px; border-top: 1px solid #e0e0e0; font-size: 10px; color: #999; text-align: center; }
@media print {
  body { padding: 0; }
  .no-print { display: none; }
}
`;

function formatDate(ts: number): string {
  return new Date(ts).toLocaleString("en-IN", {
    dateStyle: "long",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  });
}

function renderMessagePairHtml(
  userQuestion: string | undefined,
  message: Message,
): string {
  const data = extractReportData(message);
  const responseContent = data.insight || data.answer || message.content;
  const responseHtml = markdownToHtml(responseContent);

  let html = '<div class="message-pair">';

  // Question
  if (userQuestion) {
    html += `
      <div class="question-block">
        <div class="label">Question</div>
        <div class="text">${escapeHtml(userQuestion)}</div>
      </div>`;
  }

  // Response
  html += `<div class="response">${responseHtml}</div>`;

  // SQL queries
  if (data.sqls.length > 0) {
    html += '<div class="sql-section"><h3>SQL Queries</h3>';
    for (const sql of data.sqls) {
      html += `<pre><code>${escapeHtml(sql)}</code></pre>`;
    }
    html += "</div>";
  }

  // Enrichment traces
  if (data.enrichmentTraces.length > 0) {
    html += '<div class="traces"><h3>Analysis Sources</h3>';
    for (const trace of data.enrichmentTraces) {
      html += `
        <div class="trace-card">
          <div class="cat">Source [${trace.source_index}] — ${escapeHtml(trace.category)}</div>
          <div class="q">${escapeHtml(trace.question)}</div>
          ${trace.final_sql ? `<pre style="font-size:11px;background:#f5f5f5;padding:8px;border-radius:4px;margin:4px 0">${escapeHtml(trace.final_sql)}</pre>` : ""}
          ${trace.final_answer ? `<div class="ans">${markdownToHtml(trace.final_answer)}</div>` : ""}
          ${trace.duration_ms ? `<div style="font-size:11px;color:#999;margin-top:4px">${(trace.duration_ms / 1000).toFixed(1)}s</div>` : ""}
        </div>`;
    }
    html += "</div>";
  }

  // Metrics
  const metrics: string[] = [];
  if (data.generationTimeMs)
    metrics.push(`${(data.generationTimeMs / 1000).toFixed(1)}s`);
  if (data.inputTokens) metrics.push(`${data.inputTokens.toLocaleString()} input tokens`);
  if (data.outputTokens) metrics.push(`${data.outputTokens.toLocaleString()} output tokens`);
  if (metrics.length > 0) {
    html += `<div class="metrics">${metrics.join("  ·  ")}</div>`;
  }

  html += "</div>";
  return html;
}

function wrapInDocument(title: string, bodyHtml: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(title)}</title>
  <style>${REPORT_CSS}</style>
</head>
<body>
${bodyHtml}
</body>
</html>`;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Export a single message exchange (user question + assistant response)
 * as a formatted PDF via the browser's print dialog.
 */
export function downloadMessageReport(
  message: Message,
  userQuestion?: string,
  conversationTitle?: string,
) {
  const title = conversationTitle || "InsightXpert Analysis Report";

  const bodyHtml = `
    <div class="header">
      <h1>InsightXpert — Analysis Report</h1>
      <div class="meta">${formatDate(message.timestamp)}</div>
    </div>
    ${renderMessagePairHtml(userQuestion, message)}
    <div class="footer">InsightXpert — AI-Powered Data Analytics</div>
  `;

  openPrintWindow(wrapInDocument(title, bodyHtml));
}

/**
 * Export an entire conversation as a formatted PDF via the browser's
 * print dialog.
 */
export function downloadConversationReport(conversation: Conversation) {
  const title = conversation.title || "InsightXpert Conversation Report";
  const messages = conversation.messages;

  let pairsHtml = "";
  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    if (msg.role === "assistant") {
      // Find preceding user message
      const userQ =
        i > 0 && messages[i - 1].role === "user"
          ? messages[i - 1].content
          : undefined;
      pairsHtml += renderMessagePairHtml(userQ, msg);
      if (i < messages.length - 1) pairsHtml += '<div class="divider"></div>';
    }
  }

  // If no assistant messages, render user messages
  if (!pairsHtml) {
    for (const msg of messages) {
      pairsHtml += `<div class="question-block"><div class="label">${msg.role}</div><div class="text">${escapeHtml(msg.content)}</div></div>`;
    }
  }

  const bodyHtml = `
    <div class="header">
      <h1>InsightXpert — Conversation Report</h1>
      <div class="meta">
        ${escapeHtml(title)}<br>
        ${formatDate(conversation.createdAt)}
        ${conversation.messages.length > 0 ? ` — ${conversation.messages.length} messages` : ""}
      </div>
    </div>
    ${pairsHtml}
    <div class="footer">InsightXpert — AI-Powered Data Analytics</div>
  `;

  openPrintWindow(wrapInDocument(title, bodyHtml));
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function openPrintWindow(html: string) {
  // Use a blob URL so we avoid the deprecated document.write API
  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const win = window.open(url, "_blank");
  if (!win) {
    // Popup blocked — fallback to direct download
    const a = document.createElement("a");
    a.href = url;
    a.download = "insightxpert-report.html";
    a.click();
    URL.revokeObjectURL(url);
    return;
  }
  // Fallback: revoke after a timeout in case onload never fires
  const timer = setTimeout(() => URL.revokeObjectURL(url), 60_000);
  win.onload = () => {
    clearTimeout(timer);
    win.print();
    URL.revokeObjectURL(url);
  };
}
