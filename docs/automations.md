# Automations

Automations let you schedule SQL queries to run on a recurring basis and receive notifications when the results meet conditions you define.

---

## How It Works

```
Schedule fires -> SQL queries run in sequence -> Trigger conditions evaluated -> Notification sent (if conditions met)
```

1. **Schedule** -- a cron expression controls when the automation runs (hourly, daily, weekly, monthly, or custom)
2. **Workflow** -- an ordered set of SQL blocks, each querying the transactions database
3. **Endpoint block** -- the final block whose results are fed to the trigger condition evaluator
4. **Trigger conditions** -- rules applied to the endpoint block's output; if any condition fires, a notification is created
5. **Notification** -- stored in the DB and surfaced in the UI via a notification bell with polling

---

## Automations Page

The dedicated automations page lives at `/automations` in the frontend (`frontend/src/app/automations/`). It is wrapped in an `AuthGuard` layout so only authenticated users can access it.

### Page structure

| Component | File | Purpose |
|---|---|---|
| `AutomationsPage` | `frontend/src/app/automations/page.tsx` | Top-level page with header, automation list, and workflow builder dialog |
| `AutomationsLayout` | `frontend/src/app/automations/layout.tsx` | Auth guard wrapper |
| `AutomationList` | `frontend/src/components/automations/automation-list.tsx` | Fetches and renders the list of automations on mount |
| `AutomationCard` | `frontend/src/components/automations/automation-card.tsx` | Expandable card for a single automation with inline actions |
| `WorkflowBuilder` | `frontend/src/components/automations/workflow-builder.tsx` | Full-screen dialog for creating or editing an automation workflow |

The page shows a list of all automations. Each automation card displays the name, status (active/paused), schedule, and last run date. Clicking a card expands it to show the NL query, SQL workflow steps, next run time, and run history.

### Automation card actions

| Action | Description |
|---|---|
| Toggle switch | Enable or disable the automation |
| Zap icon | Trigger the automation immediately (manual run) |
| Timer icon | Start test trigger mode -- runs the automation at a configurable interval (5--3600 seconds) |
| Pencil icon | Open the workflow builder to edit the automation |
| Trash icon | Delete the automation (with confirmation dialog) |

### Test trigger mode

Test trigger mode runs the automation repeatedly at a user-defined interval (default 30 seconds). The card shows a live status bar with iteration count, last run status, and trigger fire counts. Stop the test by clicking the stop button.

---

## Workflow Builder

The workflow builder is a full-screen dialog (`95vw x 90vh`) for creating and editing automations. It opens in two ways:

1. **From a chat conversation** -- click "Create Automation" on an assistant message that contains SQL. The builder initializes blocks from all SQL queries in the conversation.
2. **From the automations page** -- click the pencil icon on an existing automation to edit it.

### Layout

The builder has three areas: **Header**, **Body** (sidebar + canvas), and **Footer**.

### Header

| Field | Description |
|---|---|
| **Name** (required) | The automation name |
| **Description** | Optional description of what the automation monitors |

### Sidebar

The sidebar (`WorkflowSidebar`, 320px wide) has four collapsible sections:

| Section | Icon | Purpose |
|---|---|---|
| **Query Library** | Library | All SQL queries from the source conversation. Click a card to add it to the canvas. Shows table tags extracted from SQL. Queries already on the canvas are dimmed. |
| **AI Generator** | Sparkles | Generate a new SQL query from a natural-language prompt using the analyst agent (`POST /api/automations/generate-sql`). The generated block is added to the canvas. |
| **Schedule** | Calendar | Pick Hourly / Daily / Weekly / Monthly / Custom (cron). |
| **Trigger Conditions** | Bell | Define when a notification fires (see below). Includes trigger template load/save and the condition builder. Columns are auto-populated from the endpoint block's result preview. |

### Canvas

The canvas (`WorkflowCanvas`) uses React Flow (`@xyflow/react`) for a node-based visual editor. SQL blocks are rendered as custom `SQLBlockNode` components with drag-and-drop positioning, snapped to a 16px grid.

**Block features:**

| Element | Description |
|---|---|
| Top handle | Input connection point -- drag a connection from another block's bottom handle here |
| Bottom handle | Output connection point -- drag from here to another block's top handle |
| SQL preview | Scrollable preview of the SQL (up to 500 chars). Click to open the full SQL editor. |
| Footer | Shows row/column counts from result preview, or the source user question |

**Block actions (header bar):**

| Icon | Action |
|---|---|
| Code2 | Open the SQL editor modal to view, edit, run the query, and see results inline |
| Toggle switch | Enable / disable this block (disabled blocks are skipped during execution) |
| Target | Mark as the **endpoint** block (trigger conditions evaluate this block's output). Auto-executes SQL if no result preview exists. |
| Pencil | Rename the block label inline |
| Trash | Remove block from canvas (also removes connected edges) |

**Edge features:**

- Drag from a block's bottom handle to another block's top handle to create a connection
- Animated edges with arrow markers show execution flow
- **Auto-connect** -- when blocks share referenced tables, dashed suggested edges appear. Click "Auto-connect" to accept all suggestions.
- Delete edges with the Delete key

**Execution order** is determined by topological sort (Kahn's algorithm) over active, connected blocks. Disconnected blocks are appended in Y-position order.

### SQL Editor Modal

Clicking the code icon or the SQL preview opens the `SqlEditorModal`:

- Edit the SQL directly in a full editor
- Run it live against the database with **Run SQL** (or Ctrl+Enter) via `POST /api/sql/execute`
- Results show inline in a scrollable table
- Click **Save Changes** to update the block in the workflow

### Footer

| Control | Description |
|---|---|
| Block count | Shows how many active blocks are on the canvas and whether an endpoint is set |
| **Test Run** | (Edit mode only) Runs the saved automation immediately and shows the result inline |
| **Cancel** | Close without saving |
| **Create / Update Automation** | Save the automation |

---

## Trigger Conditions

Trigger conditions determine **when you get notified**. If you leave them empty, every scheduled run records a `success` status but no notification is created.

Each condition has a **type**:

| Type | What it checks |
|---|---|
| `threshold` | A numeric column in the endpoint output crosses a value (gt, gte, lt, lte, eq, ne) |
| `row_count` | The number of rows returned crosses a threshold |
| `change_detection` | A column's value changed by N% compared to the previous run |
| `column_expression` | A column value across rows meets a condition (scope: `any_row` or `all_rows`) |
| `slope` | A numeric column's trend across recent runs (linear regression over `slope_window` data points, default 5) |

**AI Trigger (Beta)** -- describe the condition in plain English (e.g. "alert when daily transaction count drops below 500") and the system compiles it into a structured condition via `POST /api/automations/compile-trigger`. The LLM is prompted to output a JSON condition matching one of the five types.

Only the **endpoint block** is evaluated. Mark the target block in your pipeline as the endpoint using the Target icon.

### Trigger Templates

Trigger condition sets can be saved as reusable templates via the `TriggerTemplatePicker` component. Templates are stored server-side and scoped by organization.

| Action | Description |
|---|---|
| **Load** | Select a saved template to populate the condition builder |
| **Save as Template** | Save the current conditions under a name for reuse |
| **Delete** | Remove a template |

---

## Scheduling

| Preset | Cron |
|---|---|
| Hourly | `0 * * * *` |
| Daily | `0 9 * * *` (9 AM) |
| Weekly | `0 9 * * 1` (Monday 9 AM) |
| Monthly | `0 9 1 * *` (1st of month 9 AM) |
| Custom | Any valid 5-field cron expression |

The scheduler runs in the backend via `AutomationScheduler` (APScheduler `AsyncIOScheduler`). Each automation gets its own job keyed by its `id`. On startup, all active automations are loaded and scheduled. The scheduler supports `pause_job`, `resume_job`, `reschedule_job`, `remove_job`, and `run_now` operations.

---

## Notifications

When trigger conditions fire, a `Notification` is created for the automation's owner. Notifications have a severity level (`info`, `warning`, `critical`) and include the fired trigger messages.

### Notification UI

| Component | File | Purpose |
|---|---|---|
| `NotificationBell` | `frontend/src/components/notifications/notification-bell.tsx` | Header bell icon with unread count badge, polls every 30 seconds |
| `NotificationPopover` | `frontend/src/components/notifications/notification-popover.tsx` | Dropdown showing recent unread notifications |
| `NotificationAllModal` | `frontend/src/components/notifications/notification-all-modal.tsx` | Full modal listing all notifications (admin view includes user info) |
| `NotificationCard` | `frontend/src/components/notifications/notification-card.tsx` | Individual notification display |
| `NotificationDetailModal` | `frontend/src/components/notifications/notification-detail-modal.tsx` | Detailed view of a single notification |

### Notification store

The `useNotificationStore` (Zustand) manages notification state with optimistic updates:

- `fetchNotifications(unreadOnly?)` -- fetch current user's notifications
- `fetchAllNotifications(unreadOnly?)` -- fetch all notifications (admin-scoped)
- `fetchUnreadCount()` -- fetch unread count for badge
- `markAsRead(id)` -- optimistic mark-as-read with rollback on failure
- `markAllAsRead()` -- optimistic mark-all-as-read with rollback on failure

---

## API Endpoints

### Automations (`/api/automations`)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/automations` | Admin | Create a new automation |
| GET | `/api/automations` | Admin | List automations (org-scoped for org admins, all for super admins) |
| GET | `/api/automations/{id}` | Admin | Get automation with recent runs |
| PUT | `/api/automations/{id}` | Admin | Update an existing automation |
| DELETE | `/api/automations/{id}` | Admin | Delete an automation |
| PATCH | `/api/automations/{id}/toggle` | Admin | Enable or disable |
| POST | `/api/automations/{id}/run` | Admin | Run immediately (manual trigger) |
| GET | `/api/automations/{id}/runs` | Admin | Run history (limit 1--100, default 20) |
| GET | `/api/automations/{id}/runs/{run_id}` | Admin | Get a specific run |
| POST | `/api/automations/compile-trigger` | Admin | Compile NL text into a TriggerCondition |
| POST | `/api/automations/generate-sql` | Admin | Generate SQL from a natural-language prompt |

### Notifications (`/api/notifications`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/notifications` | User | List current user's notifications |
| GET | `/api/notifications/all` | Admin | List all notifications (org-scoped or global) |
| GET | `/api/notifications/count` | User | Get unread notification count |
| PATCH | `/api/notifications/{id}/read` | User | Mark a notification as read |
| POST | `/api/notifications/mark-all-read` | User | Mark all of current user's notifications as read |

### Trigger Templates (`/api/trigger-templates`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/trigger-templates` | Admin | List trigger templates (org-scoped) |
| POST | `/api/trigger-templates` | Admin | Create a trigger template |
| PUT | `/api/trigger-templates/{id}` | Admin | Update a trigger template |
| DELETE | `/api/trigger-templates/{id}` | Admin | Delete a trigger template |

### SQL Execution

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/sql/execute` | Admin | Run a read-only SQL query (used by SQL editor in the workflow builder) |

---

## Data Model

```
Automation (automations)
  id                        PK, UUID
  name                      VARCHAR(255)
  description               TEXT, nullable
  nl_query                  TEXT
  sql_query                 TEXT (JSON array of SQL strings, or legacy single string)
  cron_expression           VARCHAR(100)
  trigger_conditions        TEXT (JSON blob, kept for backward compat)
  is_active                 BOOLEAN, default true
  last_run_at               DATETIME, nullable
  next_run_at               DATETIME, nullable
  created_by                FK -> users.id (CASCADE)
  org_id                    FK -> organizations.id (SET NULL), nullable
  source_conversation_id    VARCHAR(36), nullable
  source_message_id         VARCHAR(36), nullable
  workflow_json             TEXT (serialized workflow graph), nullable
  created_at                DATETIME
  updated_at                DATETIME

AutomationTrigger (automation_triggers)
  id                        PK, UUID
  automation_id             FK -> automations.id (CASCADE)
  ordinal_position          INTEGER
  type                      VARCHAR(50) -- threshold, row_count, change_detection, column_expression, slope
  column                    VARCHAR(255), nullable
  operator                  VARCHAR(10), nullable -- gt, gte, lt, lte, eq, ne
  value                     FLOAT, nullable
  change_percent            FLOAT, nullable
  scope                     VARCHAR(20), nullable -- any_row, all_rows
  slope_window              INTEGER, nullable
  nl_text                   TEXT, nullable
  created_at                DATETIME
  updated_at                DATETIME

AutomationRun (automation_runs)
  id                        PK, UUID
  automation_id             FK -> automations.id (CASCADE)
  status                    VARCHAR(20) -- success, no_trigger, error
  result_json               TEXT (JSON), nullable
  row_count                 INTEGER, nullable
  execution_time_ms         INTEGER, nullable
  triggers_fired            TEXT (JSON), nullable
  error_message             TEXT, nullable
  created_at                DATETIME

Notification (notifications)
  id                        PK, UUID
  user_id                   FK -> users.id (CASCADE)
  automation_id             FK -> automations.id (CASCADE), nullable
  run_id                    FK -> automation_runs.id (SET NULL), nullable
  title                     VARCHAR(500)
  message                   TEXT
  severity                  VARCHAR(20) -- info, warning, critical
  is_read                   BOOLEAN, default false
  created_at                DATETIME

TriggerTemplate (trigger_templates)
  id                        PK, UUID
  name                      VARCHAR(255), unique
  description               TEXT, nullable
  conditions_json           TEXT (JSON)
  created_by                FK -> users.id (CASCADE)
  org_id                    FK -> organizations.id (SET NULL), nullable
  created_at                DATETIME
  updated_at                DATETIME
```

### Dual-write strategy for trigger conditions

Trigger conditions are stored in two places:
1. **JSON blob** on the `automations.trigger_conditions` column (backward compatibility)
2. **Normalized rows** in the `automation_triggers` table (one row per condition, ordered by `ordinal_position`)

On read, normalized rows take priority. The JSON blob is used as a fallback if no normalized rows exist (e.g. during migration).

---

## Backend Module Structure

```
backend/src/insightxpert/automations/
  __init__.py
  models.py         -- Pydantic request/response models (CreateAutomationRequest, TriggerCondition, etc.)
  routes.py          -- FastAPI routers: automations, notifications, trigger templates
  service.py         -- AutomationService: CRUD for automations, runs, notifications, templates (SQLAlchemy)
  scheduler.py       -- AutomationScheduler: APScheduler-based cron execution, SQL chain runner, trigger evaluation
  evaluator.py       -- TriggerEvaluator: evaluates all 5 trigger types against query results
  nl_trigger.py      -- NL-to-trigger compiler: sends description to LLM, parses structured JSON condition
```

### Execution flow (scheduler.py)

1. APScheduler fires the cron job for an automation
2. `_execute_automation(automation_id)` loads the automation from the service
3. All SQL queries in the chain are executed sequentially against the data database (max 1000 rows per query)
4. Trigger conditions are evaluated against the **last** query's result using `TriggerEvaluator`
5. For `change_detection` -- the most recent previous run's result is compared
6. For `slope` -- up to `slope_window` previous runs are loaded for linear regression
7. If any condition fires, a `Notification` is created for the automation owner
8. A `AutomationRun` record is created with status `success` (triggers fired), `no_trigger` (no triggers fired), or `error`
9. `last_run_at` and `next_run_at` timestamps are updated

### SQL validation

All SQL queries go through `_validate_single_sql()` which enforces:
- No forbidden statements (only SELECT queries allowed, checked via `FORBIDDEN_SQL_RE`)
- No multi-statement SQL (no semicolons within the body)
- Must be a complete SQL statement (`sqlite3.complete_statement()`)

---

## Frontend Module Structure

```
frontend/src/
  app/automations/
    layout.tsx                                  -- AuthGuard wrapper
    page.tsx                                    -- Main automations page
  components/automations/
    automation-list.tsx                         -- List of automation cards
    automation-card.tsx                         -- Expandable card with actions and run history
    workflow-builder.tsx                        -- Full-screen dialog for create/edit
    workflow-canvas.tsx                         -- React Flow canvas with SQL block nodes
    workflow-sidebar.tsx                        -- Sidebar with query library, AI generator, schedule, triggers
    sql-block-node.tsx                         -- Custom React Flow node for SQL blocks
    sql-editor-modal.tsx                       -- SQL editor with live execution
    schedule-picker.tsx                        -- Schedule preset/custom cron picker
    trigger-condition-builder.tsx              -- Form builder for trigger conditions
    trigger-template-picker.tsx                -- Load/save trigger templates
    condition-row.tsx                          -- Single condition row in the builder
    ai-sql-generator.tsx                       -- NL-to-SQL generator component
    run-history.tsx                            -- Run history table with expandable detail
    run-detail-modal.tsx                       -- Detailed view of a single run
  components/notifications/
    notification-bell.tsx                      -- Header bell with unread count (polls every 30s)
    notification-popover.tsx                   -- Dropdown of recent unread notifications
    notification-all-modal.tsx                 -- Full notification list modal
    notification-card.tsx                      -- Single notification display
    notification-detail-modal.tsx              -- Detailed notification view
    notification-list.tsx                      -- Notification list layout
    notification-shared.tsx                    -- Shared notification utilities
  stores/
    automation-store.ts                        -- Zustand store: CRUD, workflow builder state, test triggers
    notification-store.ts                      -- Zustand store: notifications with optimistic updates
  types/
    automation.ts                              -- TypeScript interfaces for all automation types
  lib/
    automation-utils.ts                        -- Helpers: cronToHumanReadable, SCHEDULE_PRESETS, operator labels
```

### Automation store key features

- **Workflow builder state**: blocks, edges, open/close, editing automation ID
- **Topological sort**: Kahn's algorithm orders SQL blocks by edge connections for the execution chain
- **Block initialization**: `initBlocksFromConversation()` walks assistant messages, extracts SQL chunks, pairs with user questions, and auto-marks the endpoint
- **AI SQL generation**: `generateSQL(prompt)` calls the backend analyst agent and adds the result as a new block
- **Test triggers**: `startTestTrigger(id, intervalSeconds)` runs the automation on a client-side interval with live status tracking

---

## Access Control

- **Automation CRUD, manual runs, templates**: require admin role (`require_admin_user`)
- **Automation listing**: org-scoped for org admins, global for super admins (`get_admin_context`)
- **Notifications (own)**: require authenticated user (`get_current_user`)
- **Notifications (all)**: require admin role, org-scoped for org admins
- **Resource scoping**: `assert_resource_in_scope` ensures org admins can only access resources in their organization

---

## Current Limitations

- SQL queries are read-only (SELECT / WITH / EXPLAIN only)
- Trigger condition evaluation happens server-side in `automations/scheduler.py`
- Notifications are polled every 30 seconds via `GET /api/notifications/count` (no WebSocket push)
- Test Run is only available when editing a saved automation (not during initial creation)
- The SQL editor in the workflow builder saves changes to the local store; they are persisted when you click "Create / Update Automation"
- Each SQL query in the chain returns a maximum of 1000 rows
- Slope trigger requires at least 2 data points (current + 1 previous run)
