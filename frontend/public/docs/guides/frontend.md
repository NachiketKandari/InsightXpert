# Frontend Documentation

## Stack Overview

| Concern | Library / Version |
|---|---|
| Framework | Next.js 16 (App Router) |
| UI runtime | React 19 |
| Language | TypeScript (strict) |
| Styling | Tailwind CSS 4 (utility-first) |
| Component primitives | Shadcn/ui + Radix UI (accessible) |
| Client state | Zustand 5 |
| Animation | Framer Motion 12 |
| Data visualization | Recharts 2 |
| Streaming | Custom SSE client (`sse-client.ts`) |
| Workflow canvas | `@xyflow/react` (React Flow) 12 |
| Markdown | react-markdown + remark-gfm |
| Syntax highlighting | react-syntax-highlighter |
| Toast notifications | Sonner |

Fonts: Inter (body), JetBrains Mono (code). Both loaded via `next/font/google` and applied as CSS variables.

---

## Pages / Routes

| Route | Auth required | Notes |
|---|---|---|
| `/` | Yes (`AuthGuard`) | Main chat interface |
| `/login` | No | Email + password login form |
| `/register` | No | Registration form |
| `/automations` | Yes (`AuthGuard`) | Automation list + workflow builder (standalone page, not under `/admin`) |
| `/admin` | Yes + `is_admin` | Admin dashboard |
| `/admin/automations` | Yes + `is_admin` | Automation workflow builder (mounts `WorkflowBuilder` dialog immediately on load) |
| `/admin/notifications` | Yes + `is_admin` | Notification management |

`AuthGuard` (`components/auth/auth-guard.tsx`) calls `checkAuth()` on mount. If the user is not authenticated it redirects to `/login`; if the user lacks `is_admin` it redirects from admin routes to `/`.

The `/automations` route has its own layout (`app/automations/layout.tsx`) that wraps children in `AuthGuard`. The page renders a sticky header with a back-link to `/`, an `AutomationList`, a `WorkflowBuilder` dialog, and a `ConfirmDialog` for delete confirmation.

---

## App Shell

`AppShell` (`components/layout/app-shell.tsx`) wraps the main chat page. All authenticated pages go through it.

### Header

Located at the top of `AppShell`. Contains:

- Left sidebar toggle button
- `AppLogo`
- Dataset selector (`DatasetSelector` dropdown; see Dataset Components below)
- Model switcher (reads from `settings-store`, calls `POST /api/config/switch`)
- Documentation button (`DocsDialog`; see Layout Components below)
- Insight bell (`InsightBell`) with unread badge
- Notification bell (`NotificationBell`) with unread badge
- User menu (theme toggle, admin link if `is_admin`, logout)

### Left Sidebar

`LeftSidebar` (`components/layout/left-sidebar.tsx`). Fixed width 308px on desktop; overlays on mobile. State is held in `chat-store` (`leftSidebarOpen`). Contains:

- "Chat History" heading with search icon and close button
- Debounced search input (300ms, min 2 chars, calls `GET /api/conversations/search?q=`)
- "New Chat" button (calls `clearActiveConversation()`)
- `ConversationList` (scrollable) — or `SearchResults` when search is active
- `UserMenu` pinned at the bottom

Conversation items support rename and delete via a context menu (right-click or `…` button). Rename calls `PATCH /api/conversations/:id`; delete calls `DELETE /api/conversations/:id`.

### Right Sidebar

`RightSidebar` (`components/layout/right-sidebar.tsx`). Fixed width 330px on desktop; overlays on mobile. State is held in `chat-store` (`rightSidebarOpen`). Contains:

- "Agent Process" heading with close button
- `ProcessSteps` in a scroll area

### Health Check Gate

`HealthCheckGate` (`components/health/health-check-gate.tsx`) wraps the entire app in `layout.tsx`. It polls `GET /api/health` until the backend responds with 200, showing a loading spinner until then. This prevents users from interacting before the server is ready.

### Mobile Behavior

Both sidebars collapse to overlays on viewports below the `md` breakpoint (768px). `useMediaQuery` detects the breakpoint.

---

## Chat Components

### `ChatPanel`

`components/chat/chat-panel.tsx` — top-level chat orchestrator. Reads `activeConversation()` from `chat-store`. Renders one of:

1. A spinner while `isLoadingConversation` is true
2. `MessageList` + `MessageInput` when the conversation has messages
3. `WelcomeScreen` when starting a new conversation

`handleSend` calls `useSSEChat().sendMessage(message, agentMode)`.

### `WelcomeScreen`

`components/chat/welcome-screen.tsx` — shown when no messages exist. Displays categorised sample question prompts. Clicking a prompt sends it immediately via `onSendMessage`. Also exposes the sample questions modal trigger.

### `MessageInput`

`components/chat/message-input.tsx` — auto-growing textarea. Enter submits; Shift+Enter inserts a newline. Shows a stop button during streaming. Also contains `InputToolbar`.

### `InputToolbar`

Sits below `MessageInput`. Contains:

- **Plus menu** (`+` button) — dropdown with "Upload CSV" (opens `CsvUploadDialog`), "Upload Document" (opens `PdfUploadDialog`), "SQL Executor" (if feature-enabled), and analysis mode selection
- **Agent mode selector** — Basic / Agentic / Deep Think pill tag, persisted in `settings-store`. During streaming the pill switches to show the current agent phase (e.g. "Orchestrating", "Analyzing", "Deep Thinking") as a static label
- **Model switcher** — provider/model dropdown (shown when `model_switching` feature is enabled)
- **Voice input button** — microphone icon that toggles voice recording (see `useVoiceInput` hook below). While recording, displays an animated 5-bar waveform button (`VoiceWaveButton`); while requesting mic permission, shows a spinner
- **Send / Stop button** — send arrow when idle, stop square during streaming
- **Voice error** — inline red error text shown below the toolbar when `voiceError` is set

### `MessageList`

`components/chat/message-list.tsx` — renders all messages in the active conversation. Auto-scrolls to the bottom when `messages.length` or the last message's chunk count changes (avoids scroll-jacking on feedback or mid-stream token updates). Each message is rendered by `MessageBubble`.

### `MessageBubble`

Renders a single `Message`. Assistant messages iterate over `message.chunks` and delegate each to `ChunkRenderer`. User messages render plain text. Includes `MessageActions` (copy, feedback, retry).

### `MessageActions`

Appears on hover below each message. Provides:

- Copy user prompt
- Copy assistant response
- Thumbs-up / thumbs-down feedback (calls `POST /api/conversations/:id/messages/:msgId/feedback`)
- Retry (re-sends the original user message)

---

## Chunk Renderers

`chunk-renderer.tsx` dispatches each `ChatChunk` to a typed component. The full set of chunk types is defined in `types/chat.ts`:

| Chunk type | Component | Description |
|---|---|---|
| `status` | `StatusChunk` | Progress bar / spinner with message label |
| `sql` | `SqlChunk` | Syntax-highlighted SQL with copy button |
| `tool_call` | `ToolCallChunk` | Tool name and arguments display |
| `tool_result` | `ToolResultChunk` | Collapsible data table or raw result via `parseToolResult()` |
| `answer` | `AnswerChunk` | `React.memo`'d markdown renderer (react-markdown + remark-gfm) |
| `insight` | `InsightChunk` | Cited markdown with `[[N]]` citation markers; primary sections always visible, secondary sections collapsible |
| `error` | `ErrorChunk` | Red error message |
| `clarification` | `ClarificationChunk` | Clarifying question with answer input and "Just answer" skip button |
| `stats_context` | `StatsContextChunk` | Shows pre-computed stats injected as context |
| `orchestrator_plan` | Handled in `useSSEChat` | Adds an agent step; plan surfaced via `ThinkingTrace` |
| `agent_trace` | Handled in `useSSEChat` | Adds an agent step with duration and success state |
| `enrichment_trace` | Stored in chunks | Backing data for `[[N]]` citation links in `InsightChunk` |
| `metrics` | Handled in `appendChunk` | Updates `inputTokens`, `outputTokens`, `generationTimeMs` on the message; never rendered directly |

Supplementary components:

- **`ChartBlock`** (`components/chunks/chart-block.tsx`) — auto-renders a Recharts chart from `tool_result` data. Chart type is determined by `detectChartType()`.
- **`DataTable`** (`components/chunks/data-table.tsx`) — sortable, paginated table rendered from SQL result rows.
- **`ThinkingTrace`** (`components/chunks/thinking-trace.tsx`) — collapsible agentic mode trace showing `OrchestratorPlan` tasks, per-task `AgentTrace` duration and success, and a "View full trace" link that opens `TraceModal`.
- **`CitationLink`** (`components/chunks/citation-link.tsx`) — inline `[N]` badge that opens `TraceModal` for the corresponding enrichment trace.
- **`TraceModal`** (`components/chunks/trace-modal.tsx`) — modal showing the full `EnrichmentTrace` for a citation (steps, SQL, final answer).

---

## Chart Detection

`lib/chart-detector.ts` auto-detects chart type from SQL result columns and rows.

Detection priority:

1. **`grouped-bar`** — exactly 2 category columns + 1 numeric column, more than 2 rows
2. **`pie`** — 2–10 rows, exactly 1 category column + 1 numeric column
3. **`line`** — any column name matching `/\b(date|month|year|day|week|quarter|time|period|created_at|updated_at)\b/i` with 3+ rows
4. **`bar`** — 1+ category columns + 1+ numeric columns with more than 1 row
5. **`none`** — fewer than 2 columns or no rows

Additional helpers:

- `getChartConfig()` — extracts `categoryKey`, `valueKey`, `groupKey` for Recharts props
- `pivotData()` — pivots rows for grouped-bar charts using a map-based accumulation
- `abbreviateState()` / `hasStateCategories()` — converts Indian state names to RTO two-letter codes on chart axes to prevent label overflow

User can override the detected chart type via `ChartConfigurator` (`components/sql/chart-configurator.tsx`).

---

## Streaming (SSE Client)

### `sse-client.ts`

`createSSEStream(message, conversationId, callbacks, agentMode, options)` opens an HTTP streaming connection to `POST /api/chat`. It:

1. POSTs `{ message, conversation_id, agent_mode, skip_clarification? }` with `credentials: "include"`.
2. Reads the response body as a `ReadableStream`, decoding line-by-line.
3. Parses `data: <json>` SSE lines. `[DONE]` ends the stream.
4. Enqueues chunks and drains them via `queueMicrotask` so all chunks from the same `reader.read()` batch are processed together, exploiting React 18 automatic batching.

Returns an `AbortController` so the caller can cancel in-flight streams.

`AgentMode` is one of `"basic" | "agentic" | "deep"`.

### `useSSEChat` hook

`hooks/use-sse-chat.ts` is the main chat hook. It:

- Calls `createSSEStream` and dispatches each chunk to `chat-store` (`appendChunk`, `addAgentStep`, `updateAgentStep`).
- Tracks `lastRunningStepId` to mark the previous running step as `"done"` when the next phase begins.
- On `[DONE]`, records wall-clock time (`updateLastAssistantTime`) and calls `finishStreaming`.
- On stream error, appends an error chunk and calls `finishStreaming`.
- If the stream emitted an `insight` chunk, refreshes the insight badge count via `useInsightStore.getState().fetchCount()`.

---

## State Management (Zustand Stores)

### `auth-store.ts`

Holds `user: AuthUser | null` (`{ id, email, is_admin }`), `isLoading`, `error`. Not persisted — session state is managed by the server via HttpOnly cookies. Actions: `login`, `register`, `logout`, `checkAuth`.

### `chat-store.ts`

Persisted to `sessionStorage` (key `"insightxpert-chat"`). Persists conversation list but strips message arrays on save (messages are lazy-loaded from the server).

Key state:

- `conversations: Conversation[]` — full message arrays in memory, titles + IDs in sessionStorage
- `activeConversationId: string | null`
- `isStreaming: boolean`, `streamingConversationId: string | null`
- `agentSteps: AgentStep[]` — populated during streaming by `useSSEChat`
- `leftSidebarOpen`, `rightSidebarOpen`, `sqlExecutorOpen`, `datasetViewerOpen`, `sampleQuestionsOpen`
- `pendingClarification: string | null` — set when a `clarification` chunk arrives
- `skipClarificationNext: boolean` — set when user clicks "Just answer"
- `currentAgentPhase: string | null` — tracks current agent phase label for `InputToolbar`

Conversation lifecycle: `initFromStorage()` fetches from `GET /api/conversations` and merges with any very-recent local-only conversations (< 30s old). `setActiveConversation()` lazy-loads messages for server-side conversations with no cached messages.

### `settings-store.ts`

Not persisted. Holds `currentProvider`, `currentModel`, `providers[]` (from `GET /api/config`), `agentMode: AgentMode`. `switchModel()` does an optimistic update and reverts on failure.

### `client-config-store.ts`

Fetches `GET /api/client-config` on app load. Stores `config: OrgConfig | null`, `isAdmin`, `orgId`. On response, applies org branding CSS variables and forced color mode to `document.documentElement`. Not persisted.

### `insight-store.ts`

Session store for insight badge. Holds `unreadCount` and `insights[]`. Refreshed after any chat stream that emits an `insight` chunk.

### `notification-store.ts`

Session store for notification bell. Holds `unreadCount` and `notifications[]`.

### `automation-store.ts`

Holds automation workflows (`automations[]`), run history, and workflow builder state (`workflowBuilderOpen`, `workflowBlocks`, `workflowEdges`). Topology of SQL blocks is computed via Kahn's algorithm (`topologicalSort`) before saving. Persisted to localStorage.

---

## Custom Hooks

| Hook | File | Purpose |
|---|---|---|
| `useSSEChat()` | `hooks/use-sse-chat.ts` | Manages SSE streaming, chunk dispatch, agent steps |
| `useVoiceInput(onTranscript?)` | `hooks/use-voice-input.ts` | Streams mic audio to backend for real-time speech-to-text (see below) |
| `useClientConfig()` | `hooks/use-client-config.ts` | Reads feature toggles from `client-config-store` |
| `useTheme()` | `hooks/use-theme.ts` | Dark/light mode toggle (localStorage + system preference) |
| `useAutoScroll(ref, deps)` | `hooks/use-auto-scroll.ts` | Auto-scrolls a container to bottom when deps change |
| `useMediaQuery(query)` | `hooks/use-media-query.ts` | Responsive breakpoint detection |
| `useSyntaxTheme()` | `hooks/use-syntax-theme.ts` | Returns correct syntax-highlighter theme for dark/light mode |
| `useHealthCheck()` | `hooks/use-health-check.ts` | Polls `/api/health` until backend is ready |

### `useVoiceInput`

`hooks/use-voice-input.ts` provides real-time speech-to-text via a WebSocket connection to the backend (`/api/transcribe`), which proxies audio to Deepgram Nova-3.

**State machine** (`VoiceState`): `"idle"` -> `"requesting"` (awaiting mic permission) -> `"listening"` (recording + transcribing).

**How it works:**

1. `start()` requests mic access via `getUserMedia({ audio: true })`, then opens a WebSocket to `{wsBaseUrl}/api/transcribe?token=...`.
2. A `MediaRecorder` (WebM/Opus, 250ms timeslice) sends audio binary frames over the WebSocket.
3. Incoming Deepgram JSON messages update two buffers: `committedRef` (finalized phrases) and `interimRef` (in-progress text). After each update, `emit()` pushes the full accumulated transcript (`prefix + committed + interim`) to the `onTranscript` callback.
4. On `speech_final` from Deepgram (end-of-utterance), `stop()` is called automatically.
5. A 10-second silence timer auto-stops if no speech is detected.
6. `prefixRef` accumulates text across multiple voice sessions so the user can dictate, stop, type, then dictate again without losing earlier text.
7. `clearVoiceText()` resets all buffers -- called by `MessageInput` after sending a message.

**WebSocket URL resolution:** Uses `SSE_BASE_URL` (direct to backend, bypassing CDN proxy which does not support WebSockets). Falls back to `window.location` for local development.

**Error handling:** Displays inline error text for mic denial (`"Microphone access denied"`), WebSocket failure (`"Voice connection failed"`), auth errors (WS close code 4001), and unconfigured STT (WS close code 4002).

**Returns:** `{ voiceState, voiceError, toggleVoice, clearVoiceText }`.

---

## Admin Components

Located in `components/admin/`.

- **`FeatureToggles`** — toggle switches for `sql_executor`, `model_switching`, `rag_training`, `chart_rendering`, `conversation_export`, `agent_process_sidebar`, `clarification_enabled`, `stats_context_injection` per org
- **`BrandingEditor`** (`branding-editor.tsx`) — logo URL, display name, color mode override, CSS variable theme overrides
- **`UserOrgMappings`** (`user-org-mappings.tsx`) — email → org assignment table
- **`AdminDomainEditor`** (`admin-domain-editor.tsx`) — list of admin email domain suffixes
- **`ConversationViewer`** (`conversation-viewer.tsx`) — admin view of all user conversations and messages

---

## Automations Components

Located in `components/automations/`.

- **`WorkflowBuilder`** — main dialog container, hosts canvas + sidebar + save/run controls. Opened via `automation-store`'s `workflowBuilderOpen` flag.
- **`WorkflowCanvas`** (`workflow-canvas.tsx`) — `@xyflow/react` canvas rendering `SqlBlockNode` nodes with directed edges between them
- **`WorkflowSidebar`** (`workflow-sidebar.tsx`) — trigger conditions, schedule configuration, SQL block editing
- **`AiSqlGenerator`** (`ai-sql-generator.tsx`) — natural language → SQL using `/api/chat/answer`
- **`TriggerConditionBuilder`** (`trigger-condition-builder.tsx`) — builds threshold/comparison conditions for automation triggers (e.g., `count > 100`)
- **`SchedulePicker`** (`schedule-picker.tsx`) — cron expression builder with daily, hourly, and custom presets
- **`AutomationList`** (`automation-list.tsx`) — list of saved automations with enable/disable toggle and last run status
- **`RunHistory`** (`run-history.tsx`) — chronological run log with result details
- **`SqlBlockNode`** (`sql-block-node.tsx`) — individual SQL block node on the canvas with expand/collapse

---

## Insights Components

Located in `components/insights/`.

- **`InsightBell`** — header bell icon with unread count badge. Fetches count from `insight-store`.
- **`InsightPopover`** — hover/click popover showing recent insights
- **`InsightCard`** — single insight with title, summary, and category chips
- **`InsightAllModal`** — full modal for browsing all insights (all pages)

---

## Notifications Components

Located in `components/notifications/`.

- **`NotificationBell`** — header bell icon with unread count badge
- **`NotificationPopover`** — recent notifications list
- **`NotificationCard`** — single notification with type icon
- **`NotificationDetailModal`** — full notification content

---

## Dataset Components

Located in `components/dataset/`.

### `DatasetViewer`

`dataset-viewer.tsx` — near-full-screen dialog for browsing raw dataset data. Props: `open`, `onOpenChange`, `tableName`, `datasetName`, `description`, `datasetId`.

Features:

- **Tabs:** **Data** (paginated rows) and **Columns** (column metadata, lazy-loaded on first tab switch)
- **Data tab:** 100 rows per page via `POST /api/sql/execute` with `SELECT * FROM <table> LIMIT 100 OFFSET <n>`. Sticky opaque column headers. Alternating row stripe colors. Row number column with offset-aware numbering. Auto-scrolls to top on page change.
- **Columns tab:** fetches `GET /api/datasets/public/:id/columns` and renders a grid with column name, type badge (color-coded by SQLite type), domain values (chip pills for low-cardinality columns), description, and domain rules. Only loads when the user switches to the tab.
- **Pagination footer:** shows "Page X of Y", Previous / Next buttons, row range indicator, and a CSV download button that opens `GET /api/sql/export-csv?table=<table>` in a new tab.
- **Header:** dataset name, "Read-only" badge, and total row count.

### `DatasetSelector`

`components/layout/dataset-selector.tsx` — dropdown in the header to switch the active dataset context. Fetches `GET /api/datasets/public` on mount.

Features:

- Lists all datasets with a checkmark on the active one
- Click a dataset to activate it (`POST /api/datasets/:id/activate`) with optimistic local state update
- **Eye icon** per dataset opens `DatasetViewer` for preview
- **Delete icon** per dataset (visible only if the user owns the dataset or is admin; seeded datasets with no `created_by` cannot be deleted). Calls `DELETE /api/datasets/:id` with a `window.confirm` prompt.
- **"Upload CSV" action** at the bottom opens `CsvUploadDialog`
- Listens for `dataset-changed` `CustomEvent` on `window` to immediately reflect datasets uploaded from other components (e.g. the `InputToolbar` upload dialog) without requiring a full refetch

### `CsvUploadDialog`

`csv-upload-dialog.tsx` — two-step dialog for uploading CSV datasets.

**Step 1 -- Upload:** file picker (drag-to-click zone, `.csv` only, 50 MB max), dataset name input (auto-filled from file name via `formatFileName`), optional description textarea. Submits as `multipart/form-data` to `POST /api/datasets/upload`.

**Step 2 -- Profile Review:** after upload, the server returns a `DatasetProfile` with per-column stats. The dialog expands to a wide layout showing a summary bar (row count, column count) and a scrollable table of columns with:
- Column name (with null percentage)
- Type badge (color-coded: blue for TEXT, emerald for INTEGER/REAL, orange for BOOLEAN, purple for DATETIME)
- Distinct count (with "unique" indicator)
- Details (chip pills for low-cardinality values, range for numeric columns)
- Editable description input (pre-filled with smart defaults via `defaultDescription()`)

Clicking **Confirm** calls `POST /api/datasets/:id/confirm` with the column descriptions and profile, dispatches a `dataset-changed` `CustomEvent` on `window`, and calls `onUploadSuccess`.

### `PdfUploadDialog`

`pdf-upload-dialog.tsx` — dialog for uploading PDF documents as analysis context.

**Upload form:** file picker (`.pdf` only, 20 MB max), document name input (auto-filled from file name), optional description. Submits as `multipart/form-data` to `POST /api/documents/upload`.

**Result view:** after successful upload, shows document name, original file name, page count, and a scrollable preview of the extracted text. Clicking **Done** closes the dialog and calls `onUploadSuccess`.

---

## Layout Components

Located in `components/layout/`.

### `DocsDialog`

`docs-dialog.tsx` — full documentation browser accessible from the header via a book icon button with tooltip.

**Structure:** opens a wide dialog (95vw, max 5xl, 80vh) with a two-panel layout:
- **Left sidebar** (224px): scrollable nav with grouped document links organized into "Overview" (README, Architecture, Walkthrough, Design Patterns) and "Guides" (Agent Pipeline, Agent Tools, Agents & Modes, API Reference, Architecture Detail, Automations, Configuration, Contributing, Dataset, Frontend). Active item is highlighted with primary color and a chevron indicator.
- **Right content area:** fetches the selected markdown file from the `/docs/` public path, renders it with `ReactMarkdown` + `remark-gfm` using custom styled components for headings, paragraphs, lists, code blocks, tables, links, and blockquotes.

**Behavior:** lazily fetches document content when the dialog opens or the active path changes. Shows a loading indicator while fetching.

---

## SQL Executor

`components/sql/sql-executor.tsx` — direct SQL query panel for power users. Features:

- Manual SQL input with syntax highlighting
- Submit calls `POST /api/sql/execute` (backend enforces read-only)
- Results rendered in `DataTable` with optional `ChartConfigurator`

`lib/sql-utils.ts` — SQL formatting and basic validation helpers used by the executor and automation tools.

---

## Right Sidebar: Agent Process Steps

`components/sidebar/process-steps.tsx` — renders the agentic pipeline stages as a timeline in the right sidebar. Reads `agentSteps` from `chat-store`.

Each `StepItem` (`components/sidebar/step-item.tsx`) displays:

- A status icon: spinner (running), check (done), X (error)
- A label (e.g. "Retrieved dataset statistics", "Generated SQL query")
- Optional detail text or SQL snippet in a collapsible sub-section
- Timestamp

Steps are added in real time by `useSSEChat` as chunks arrive.

---

## Utility Libraries

### `lib/file-utils.ts`

Shared helpers used by the CSV and PDF upload dialogs:

- `formatFileName(fileName)` -- strips the last file extension and converts underscores/hyphens to spaces with title case (e.g. `"q4_sales-data.csv"` becomes `"Q4 Sales Data"`)
- `formatFileSize(bytes)` -- human-readable file size string (B, KB, or MB with one decimal)

### `lib/model-utils.ts`

- `PROVIDER_LABELS` -- display names for LLM providers
- `formatModelName(model, provider)` -- prettifies model identifiers for the UI

### `lib/chart-detector.ts`

Auto-detects chart type from SQL result columns and rows (see Chart Detection section above).

### `lib/sql-utils.ts`

SQL formatting and basic validation helpers used by the SQL executor and automation tools.

---

## Types

### `types/dataset.ts`

- `DatasetInfo` -- shape of a dataset object from the API: `{ id, name, description, is_active, table_name, organization_id?, created_by }`
- `DocumentInfo` -- shape of an uploaded document: `{ id, name, description, file_name, file_type, file_size_bytes, page_count, extracted_text_preview, dataset_id, created_by, created_at }`

---

## Key Conventions

- All pages that require authentication are wrapped in `AuthGuard`.
- `chat-store` uses `sessionStorage` so conversations do not persist across browser sessions but survive page refreshes within a tab.
- `auth-store` is not persisted — it always re-validates with the server via `checkAuth()` on mount.
- SSE chunks are queued via `queueMicrotask` before delivery, exploiting React 18 batching to keep renders efficient.
- `AnswerChunk` and `InsightChunk` are wrapped with `React.memo` to avoid re-parsing markdown on unrelated state updates.
- Voice input uses WebSocket (`/api/transcribe`) for real-time audio streaming, bypassing the CDN proxy. Auth is passed via query parameter (`?token=...`) since cookies may not reach Cloud Run directly.
- Dataset change events are coordinated across components via `window.dispatchEvent(new CustomEvent("dataset-changed", { detail }))`, allowing the `DatasetSelector` in the header to stay in sync with uploads triggered from `InputToolbar` or other components without prop drilling.
- File upload dialogs (`CsvUploadDialog`, `PdfUploadDialog`) share common UX patterns: drag-to-click file zone, auto-fill name from filename via `formatFileName`, file size validation, and two-phase workflows (upload then review/confirm).
