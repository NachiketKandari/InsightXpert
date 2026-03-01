import type { Message, Conversation, ChatChunk, EnrichmentTrace, AgentTrace, OrchestratorPlan } from "@/types/chat";
import { parseToolResult } from "@/lib/chunk-parser";

// ---------------------------------------------------------------------------
// Lightweight markdown → HTML conversion (covers the patterns used by the
// InsightXpert response generator: headings, bold, italic, lists, code
// blocks, inline code, tables, blockquotes, citations, horizontal rules).
// ---------------------------------------------------------------------------

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function markdownToHtml(md: string): string {
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

  // GFM tables — header | sep | body rows (already escaped)
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
      let t = '<div class="table-wrap"><table><thead><tr>';
      for (const h of headers) t += `<th>${h}</th>`;
      t += "</tr></thead><tbody>";
      for (const row of rows) {
        t += "<tr>";
        for (const cell of row) t += `<td>${cell}</td>`;
        t += "</tr>";
      }
      t += "</tbody></table></div>";
      return t;
    },
  );

  // Horizontal rules
  html = html.replace(/^---+$/gm, "<hr>");

  // Headers
  html = html.replace(/^#### (.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

  // Bold + italic
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
  const blocks = "h[1-6]|ul|ol|pre|blockquote|table|div|hr";
  html = html.replace(new RegExp(`<p>\\s*(<(?:${blocks})[> ])`, "g"), "$1");
  html = html.replace(new RegExp(`(</(?:${blocks})>)\\s*</p>`, "g"), "$1");
  html = html.replace(/<p>\s*<\/p>/g, "");

  return html;
}

// ---------------------------------------------------------------------------
// Extract structured data from message chunks
// ---------------------------------------------------------------------------

interface DataTable {
  columns: string[];
  rows: Record<string, unknown>[];
}

interface ReportData {
  sqls: string[];
  dataTables: DataTable[];
  enrichmentTraces: EnrichmentTrace[];
  agentTraces: AgentTrace[];
  orchestratorPlan: OrchestratorPlan | null;
  answer: string;
  insight: string;
  statsContext: string;
  inputTokens?: number | null;
  outputTokens?: number | null;
  generationTimeMs?: number | null;
}

function extractReportData(message: Message): ReportData {
  const sqls: string[] = [];
  const dataTables: DataTable[] = [];
  const enrichmentTraces: EnrichmentTrace[] = [];
  const agentTraces: AgentTrace[] = [];
  let orchestratorPlan: OrchestratorPlan | null = null;
  let answer = "";
  let insight = "";
  let statsContext = "";

  for (const chunk of message.chunks) {
    if (chunk.type === "sql" && chunk.sql) sqls.push(chunk.sql);
    if (chunk.type === "tool_result") {
      const parsed = parseToolResult(chunk as ChatChunk);
      if (parsed && parsed.columns.length > 0 && parsed.rows.length > 0) {
        dataTables.push({ columns: parsed.columns, rows: parsed.rows });
      }
    }
    if (chunk.type === "enrichment_trace" && chunk.data)
      enrichmentTraces.push(chunk.data as unknown as EnrichmentTrace);
    if (chunk.type === "agent_trace" && chunk.data)
      agentTraces.push(chunk.data as unknown as AgentTrace);
    if (chunk.type === "orchestrator_plan" && chunk.data)
      orchestratorPlan = chunk.data as unknown as OrchestratorPlan;
    if (chunk.type === "answer" && chunk.content) answer = chunk.content;
    if (chunk.type === "insight" && chunk.content) insight = chunk.content;
    if (chunk.type === "stats_context" && chunk.content) statsContext = chunk.content;
  }

  return {
    sqls,
    dataTables,
    enrichmentTraces,
    agentTraces,
    orchestratorPlan,
    answer,
    insight,
    statsContext,
    inputTokens: message.inputTokens,
    outputTokens: message.outputTokens,
    generationTimeMs: message.generationTimeMs ?? message.wallTimeMs,
  };
}

// ---------------------------------------------------------------------------
// HTML report CSS
// ---------------------------------------------------------------------------

const REPORT_CSS = `
@page {
  size: A4;
  margin: 1.8cm 2cm;
  @bottom-center {
    content: counter(page);
    font-size: 9px;
    color: #999;
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
  line-height: 1.65;
  color: #1e293b;
  max-width: 780px;
  margin: 0 auto;
  padding: 40px 24px;
  background: #fff;
  font-size: 13px;
}

/* ── Header ── */
.report-header {
  margin-bottom: 32px;
  padding-bottom: 20px;
  border-bottom: 1px solid #e2e8f0;
}
.report-header .brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.report-header .brand-icon {
  width: 32px;
  height: 32px;
  background: linear-gradient(135deg, #0ea5e9, #6366f1);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 700;
  font-size: 16px;
}
.report-header h1 {
  font-size: 20px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.3px;
}
.report-header .subtitle {
  font-size: 14px;
  color: #64748b;
  margin-top: 2px;
}
.report-header .meta {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 6px;
}

/* ── Question Block ── */
.question-block {
  background: #f0f9ff;
  border-left: 3px solid #0ea5e9;
  padding: 14px 18px;
  margin: 24px 0 20px;
  border-radius: 0 8px 8px 0;
}
.question-block .label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: #0ea5e9;
  font-weight: 700;
  margin-bottom: 4px;
}
.question-block .text {
  font-size: 14px;
  color: #0f172a;
  font-weight: 500;
  line-height: 1.5;
}

/* ── Response ── */
.response { margin-top: 8px; }
.response h2 {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  margin-top: 24px;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid #e2e8f0;
}
.response h3 {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  margin-top: 18px;
  margin-bottom: 6px;
}
.response h4 {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  margin-top: 14px;
  margin-bottom: 4px;
}
.response p { margin: 6px 0; }
.response ul, .response ol { padding-left: 22px; margin: 6px 0; }
.response li { margin: 3px 0; }
.response li::marker { color: #94a3b8; }
.response strong { color: #0f172a; font-weight: 600; }
.response em { color: #475569; }
.response hr { border: none; border-top: 1px solid #e2e8f0; margin: 16px 0; }

/* ── Tables ── */
.table-wrap { overflow-x: auto; margin: 12px 0; }
table {
  border-collapse: collapse;
  width: 100%;
  font-size: 11.5px;
  line-height: 1.4;
}
th, td {
  border: 1px solid #e2e8f0;
  padding: 7px 10px;
  text-align: left;
  word-break: break-word;
}
th {
  background: #f8fafc;
  font-weight: 600;
  color: #334155;
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
td { color: #475569; }
tr:nth-child(even) td { background: #fafbfc; }

/* ── Code ── */
pre {
  background: #f1f5f9;
  padding: 14px 16px;
  border-radius: 8px;
  font-size: 11px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-wrap: break-word;
  line-height: 1.5;
  font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', Consolas, monospace;
  margin: 8px 0;
  border: 1px solid #e2e8f0;
}
code.inline {
  background: #f1f5f9;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'SF Mono', 'Fira Code', Consolas, monospace;
  color: #7c3aed;
}
.response blockquote {
  border-left: 3px solid #6366f1;
  padding: 8px 14px;
  color: #475569;
  font-style: italic;
  margin: 12px 0;
  background: #f8fafc;
  border-radius: 0 6px 6px 0;
}
.citation { color: #6366f1; font-size: 10px; vertical-align: super; font-weight: 600; }

/* ── Data Tables Section ── */
.data-section {
  margin-top: 20px;
  page-break-inside: avoid;
}
.data-section .section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
}
.data-section .section-title .icon {
  width: 16px; height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #f1f5f9;
  border-radius: 4px;
  font-size: 10px;
}
.data-badge {
  display: inline-block;
  font-size: 10px;
  color: #64748b;
  background: #f1f5f9;
  padding: 2px 8px;
  border-radius: 4px;
  margin-left: 6px;
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
}

/* ── SQL Section ── */
.sql-section { margin-top: 24px; page-break-inside: avoid; }
.sql-section .section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
}
.sql-section pre {
  background: #0f172a;
  color: #e2e8f0;
  border: none;
  border-radius: 8px;
  padding: 16px;
}

/* ── Agent Traces (Agentic / Deep Think) ── */
.plan-section {
  margin-top: 24px;
  padding: 14px 18px;
  background: #fefce8;
  border: 1px solid #fde68a;
  border-radius: 8px;
  page-break-inside: avoid;
}
.plan-section .section-title {
  font-size: 12px;
  font-weight: 600;
  color: #92400e;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}
.plan-section .reasoning {
  font-size: 12px;
  color: #78350f;
  line-height: 1.5;
  margin-bottom: 10px;
}
.plan-tasks {
  list-style: none;
  padding: 0;
}
.plan-tasks li {
  font-size: 12px;
  color: #78350f;
  padding: 4px 0;
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.plan-tasks .task-agent {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: #92400e;
  background: #fef3c7;
  padding: 1px 6px;
  border-radius: 3px;
  white-space: nowrap;
}

/* ── Analysis Sources (Traces) ── */
.traces { margin-top: 24px; }
.traces .section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
}
.trace-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 14px 16px;
  margin: 8px 0;
  page-break-inside: avoid;
}
.trace-card .trace-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.trace-card .trace-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
}
.trace-badge.cat-temporal { background: #dbeafe; color: #1e40af; }
.trace-badge.cat-segment { background: #fce7f3; color: #9d174d; }
.trace-badge.cat-comparison { background: #d1fae5; color: #065f46; }
.trace-badge.cat-trend { background: #ede9fe; color: #5b21b6; }
.trace-badge.cat-default { background: #f1f5f9; color: #475569; }
.trace-card .trace-idx {
  font-size: 10px;
  color: #94a3b8;
  font-weight: 600;
}
.trace-card .trace-status {
  font-size: 10px;
  font-weight: 600;
  margin-left: auto;
}
.trace-status.success { color: #059669; }
.trace-status.fail { color: #dc2626; }
.trace-card .trace-q {
  font-size: 13px;
  font-weight: 500;
  color: #1e293b;
  margin: 4px 0 8px;
}
.trace-card .trace-sql pre {
  font-size: 10px;
  background: #f8fafc;
  padding: 8px 12px;
  border-radius: 6px;
  margin: 6px 0;
  border: 1px solid #e2e8f0;
}
.trace-card .trace-answer { font-size: 12px; color: #475569; line-height: 1.5; }
.trace-card .trace-time { font-size: 10px; color: #94a3b8; margin-top: 6px; }

/* ── Stats Context ── */
.stats-section {
  margin-top: 20px;
  padding: 12px 16px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  page-break-inside: avoid;
}
.stats-section .section-title {
  font-size: 11px;
  font-weight: 600;
  color: #166534;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}
.stats-section .stats-content {
  font-size: 12px;
  color: #15803d;
  line-height: 1.5;
}

/* ── Metrics ── */
.metrics {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
  padding: 10px 14px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  flex-wrap: wrap;
}
.metric-pill {
  font-size: 10.5px;
  color: #64748b;
  background: #fff;
  border: 1px solid #e2e8f0;
  padding: 3px 10px;
  border-radius: 20px;
  white-space: nowrap;
  font-weight: 500;
}
.metric-pill .value { color: #334155; font-weight: 600; }

/* ── Layout ── */
.divider { border-top: 1px solid #e2e8f0; margin: 32px 0; }
.message-pair { margin-bottom: 32px; }
.footer {
  margin-top: 40px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
  text-align: center;
  color: #94a3b8;
  font-size: 10px;
  letter-spacing: 0.3px;
}

/* ── Print ── */
@media print {
  body { padding: 0; max-width: none; }
  .no-print { display: none !important; }
  .message-pair { page-break-inside: auto; }
  .trace-card, .data-section, .sql-section, .plan-section, .stats-section { page-break-inside: avoid; }
  pre { white-space: pre-wrap !important; word-break: break-all; }
  table { font-size: 10px; }
  th, td { padding: 5px 8px; }
}
`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(ts: number): string {
  return new Date(ts).toLocaleString("en-IN", {
    dateStyle: "long",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  });
}

function traceCategoryClass(category: string): string {
  const cat = category.toLowerCase();
  if (cat.includes("temporal") || cat.includes("time")) return "cat-temporal";
  if (cat.includes("segment") || cat.includes("demographic")) return "cat-segment";
  if (cat.includes("compar")) return "cat-comparison";
  if (cat.includes("trend") || cat.includes("growth")) return "cat-trend";
  return "cat-default";
}

function formatCellValue(v: unknown): string {
  if (v == null) return "-";
  if (typeof v === "number") {
    if (Number.isInteger(v)) return v.toLocaleString();
    return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return escapeHtml(String(v));
}

function renderDataTableHtml(table: DataTable, maxRows = 20): string {
  const displayRows = table.rows.slice(0, maxRows);
  const truncated = table.rows.length > maxRows;

  let html = '<div class="table-wrap"><table><thead><tr>';
  for (const col of table.columns) {
    html += `<th>${escapeHtml(col)}</th>`;
  }
  html += "</tr></thead><tbody>";
  for (const row of displayRows) {
    html += "<tr>";
    for (const col of table.columns) {
      html += `<td>${formatCellValue(row[col])}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody></table></div>";
  if (truncated) {
    html += `<div style="font-size:10px;color:#94a3b8;margin-top:4px;text-align:right">Showing ${maxRows} of ${table.rows.length} rows</div>`;
  }
  return html;
}

// ---------------------------------------------------------------------------
// Render a single message pair
// ---------------------------------------------------------------------------

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

  // Data tables from tool_result
  if (data.dataTables.length > 0) {
    html += '<div class="data-section">';
    html += `<div class="section-title">
      <span class="icon">T</span>
      Query Results
      <span class="data-badge">${data.dataTables.length} table${data.dataTables.length > 1 ? "s" : ""}</span>
    </div>`;
    for (const table of data.dataTables) {
      html += renderDataTableHtml(table);
    }
    html += "</div>";
  }

  // SQL queries
  if (data.sqls.length > 0) {
    html += '<div class="sql-section">';
    html += `<div class="section-title">
      <span class="icon" style="font-family:monospace;font-size:9px">$</span>
      SQL Queries
    </div>`;
    for (const sql of data.sqls) {
      html += `<pre><code>${escapeHtml(sql)}</code></pre>`;
    }
    html += "</div>";
  }

  // Stats context
  if (data.statsContext) {
    html += `
      <div class="stats-section">
        <div class="section-title">Dataset Statistics</div>
        <div class="stats-content">${markdownToHtml(data.statsContext)}</div>
      </div>`;
  }

  // Orchestrator plan (agentic / deep think)
  if (data.orchestratorPlan) {
    const plan = data.orchestratorPlan;
    html += '<div class="plan-section">';
    html += '<div class="section-title">Analysis Plan</div>';
    if (plan.reasoning) {
      html += `<div class="reasoning">${escapeHtml(plan.reasoning)}</div>`;
    }
    if (plan.tasks.length > 0) {
      html += '<ul class="plan-tasks">';
      for (const task of plan.tasks) {
        html += `<li>
          <span class="task-agent">${escapeHtml(task.agent)}</span>
          <span>${escapeHtml(task.task)}</span>
        </li>`;
      }
      html += "</ul>";
    }
    html += "</div>";
  }

  // Agent traces (agentic / deep think)
  if (data.agentTraces.length > 0) {
    html += '<div class="traces">';
    html += `<div class="section-title">
      <span class="icon" style="font-size:10px">A</span>
      Agent Results
      <span class="data-badge">${data.agentTraces.length} task${data.agentTraces.length > 1 ? "s" : ""}</span>
    </div>`;
    for (const trace of data.agentTraces) {
      const catClass = traceCategoryClass(trace.category ?? "");
      html += `
        <div class="trace-card">
          <div class="trace-header">
            <span class="trace-badge ${catClass}">${escapeHtml(trace.agent)}</span>
            ${trace.category ? `<span class="trace-badge ${catClass}">${escapeHtml(trace.category)}</span>` : ""}
            <span class="trace-status ${trace.success ? "success" : "fail"}">${trace.success ? "OK" : "FAILED"}</span>
          </div>
          <div class="trace-q">${escapeHtml(trace.task)}</div>
          ${trace.final_sql ? `<div class="trace-sql"><pre>${escapeHtml(trace.final_sql)}</pre></div>` : ""}
          ${trace.final_answer ? `<div class="trace-answer">${markdownToHtml(trace.final_answer)}</div>` : ""}
          ${trace.duration_ms ? `<div class="trace-time">${(trace.duration_ms / 1000).toFixed(1)}s</div>` : ""}
        </div>`;
    }
    html += "</div>";
  }

  // Enrichment traces
  if (data.enrichmentTraces.length > 0) {
    html += '<div class="traces">';
    html += `<div class="section-title">
      <span class="icon" style="font-size:10px">S</span>
      Analysis Sources
      <span class="data-badge">${data.enrichmentTraces.length} source${data.enrichmentTraces.length > 1 ? "s" : ""}</span>
    </div>`;
    for (const trace of data.enrichmentTraces) {
      const catClass = traceCategoryClass(trace.category);
      html += `
        <div class="trace-card">
          <div class="trace-header">
            <span class="trace-idx">[${trace.source_index}]</span>
            <span class="trace-badge ${catClass}">${escapeHtml(trace.category)}</span>
            <span class="trace-status ${trace.success ? "success" : "fail"}">${trace.success ? "OK" : "FAILED"}</span>
          </div>
          <div class="trace-q">${escapeHtml(trace.question)}</div>
          ${trace.final_sql ? `<div class="trace-sql"><pre>${escapeHtml(trace.final_sql)}</pre></div>` : ""}
          ${trace.final_answer ? `<div class="trace-answer">${markdownToHtml(trace.final_answer)}</div>` : ""}
          ${trace.duration_ms ? `<div class="trace-time">${(trace.duration_ms / 1000).toFixed(1)}s</div>` : ""}
        </div>`;
    }
    html += "</div>";
  }

  // Metrics
  const metricPills: string[] = [];
  if (data.generationTimeMs)
    metricPills.push(`<span class="metric-pill"><span class="value">${(data.generationTimeMs / 1000).toFixed(1)}s</span> response</span>`);
  if (data.inputTokens)
    metricPills.push(`<span class="metric-pill"><span class="value">${data.inputTokens.toLocaleString()}</span> input tokens</span>`);
  if (data.outputTokens)
    metricPills.push(`<span class="metric-pill"><span class="value">${data.outputTokens.toLocaleString()}</span> output tokens</span>`);
  if (metricPills.length > 0) {
    html += `<div class="metrics">${metricPills.join("")}</div>`;
  }

  html += "</div>";
  return html;
}

// ---------------------------------------------------------------------------
// Document wrapper
// ---------------------------------------------------------------------------

function wrapInDocument(title: string, bodyHtml: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(title)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
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
    <div class="report-header">
      <div class="brand">
        <div class="brand-icon">iX</div>
        <div>
          <h1>Analysis Report</h1>
          <div class="subtitle">${escapeHtml(title)}</div>
        </div>
      </div>
      <div class="meta">${formatDate(message.timestamp)}</div>
    </div>
    ${renderMessagePairHtml(userQuestion, message)}
    <div class="footer">InsightXpert &middot; AI-Powered Data Analytics</div>
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
  let pairCount = 0;
  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    if (msg.role === "assistant") {
      const userQ =
        i > 0 && messages[i - 1].role === "user"
          ? messages[i - 1].content
          : undefined;
      pairsHtml += renderMessagePairHtml(userQ, msg);
      pairCount++;
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
    <div class="report-header">
      <div class="brand">
        <div class="brand-icon">iX</div>
        <div>
          <h1>Conversation Report</h1>
          <div class="subtitle">${escapeHtml(title)}</div>
        </div>
      </div>
      <div class="meta">
        ${formatDate(conversation.createdAt)}
        &middot; ${pairCount} exchange${pairCount !== 1 ? "s" : ""}
        &middot; ${conversation.messages.length} messages
      </div>
    </div>
    ${pairsHtml}
    <div class="footer">InsightXpert &middot; AI-Powered Data Analytics</div>
  `;

  openPrintWindow(wrapInDocument(title, bodyHtml));
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function openPrintWindow(html: string) {
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
