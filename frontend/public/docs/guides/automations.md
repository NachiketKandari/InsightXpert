# Automations

Automations let you schedule SQL queries to run on a recurring basis and receive notifications when the results meet conditions you define.

---

## How It Works

```
Schedule fires → SQL queries run in sequence → Trigger conditions evaluated → Notification sent (if conditions met)
```

1. **Schedule** — a cron expression controls when the automation runs (hourly, daily, weekly, monthly, or custom)
2. **Workflow** — an ordered set of SQL blocks, each querying the transactions database
3. **Endpoint block** — the final block whose results are fed to the trigger condition evaluator
4. **Trigger conditions** — rules applied to the endpoint block's output; if all conditions pass (or none are defined), a notification is created
5. **Notification** — stored in the DB and surfaced in the UI when the automation fires

---

## Workflow Builder

Open the builder from any chat conversation by clicking **"Create Automation"** on an assistant message that contains SQL. The builder has three areas:

### Sidebar

| Section | Purpose |
|---|---|
| **Query Library** | All SQL queries from the current conversation. Click a card to add it to the canvas. Hover a card to see the full SQL. |
| **AI Generator** | Generate a new SQL query from a natural-language prompt. |
| **Schedule** | Pick Hourly / Daily / Weekly / Monthly / Custom (cron). |
| **Trigger Conditions** | Define when a notification fires (see below). |

### Canvas

Drag SQL blocks to reorder them. Connect blocks by dragging from the **bottom handle** of one block to the **top handle** of another. The connection order determines execution sequence.

**Block actions (hover the block header):**

| Icon | Action |
|---|---|
| `<>` (Code2) | Open the SQL editor to view, edit, and run the query |
| Toggle | Enable / disable this block (disabled blocks are skipped) |
| Target | Mark as the **endpoint** block (trigger conditions evaluate this block's output) |
| Trash | Remove block from canvas |

**SQL Editor** (click the code icon or click the SQL preview):
- Edit the SQL directly in a full editor
- Run it live against the database with **Run SQL** (or Ctrl+Enter)
- Results show inline in a scrollable table
- Click **Save Changes** to update the block in the workflow

### Footer

| Control | Description |
|---|---|
| Block count | Shows how many active blocks are on the canvas |
| **Test Run** | (Edit mode only) Runs the saved automation immediately and shows the result inline |
| **Cancel** | Close without saving |
| **Create / Update Automation** | Save the automation |

---

## Trigger Conditions

Trigger conditions determine **when you get notified**. If you leave them empty, every scheduled run sends a notification.

Each condition has a **type**:

| Type | What it checks |
|---|---|
| `threshold` | A numeric column in the endpoint output crosses a value (gt, gte, lt, lte, eq, ne) |
| `row_count` | The number of rows returned crosses a threshold |
| `change_detection` | A column's value changed compared to the previous run |
| `column_expression` | A raw SQL expression evaluated against the result |
| `slope` | A numeric column's trend (positive / negative / flat) |

**AI Trigger (Beta)** — describe the condition in plain English (e.g. "alert when daily transaction count drops below 500") and the system compiles it into a structured condition.

Only the **endpoint block** is evaluated. Mark the final block in your pipeline as the endpoint using the Target icon.

---

## Scheduling

| Preset | Cron |
|---|---|
| Hourly | `0 * * * *` |
| Daily | `0 9 * * *` (9 AM) |
| Weekly | `0 9 * * 1` (Monday 9 AM) |
| Monthly | `0 9 1 * *` (1st of month 9 AM) |
| Custom | Any valid cron expression |

The scheduler runs in the backend via `AutomationScheduler` (APScheduler). Each automation gets its own job keyed by `automation_{id}`.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/automations` | List all automations |
| POST | `/api/automations` | Create a new automation |
| PUT | `/api/automations/{id}` | Update an existing automation |
| DELETE | `/api/automations/{id}` | Delete an automation |
| PATCH | `/api/automations/{id}/toggle` | Enable or disable |
| POST | `/api/automations/{id}/run` | Run immediately (test trigger) |
| GET | `/api/automations/{id}/runs` | Run history |
| POST | `/api/automations/compile-trigger` | Compile NL text → TriggerCondition |
| POST | `/api/sql/execute` | Run a read-only SQL query (used by SQL editor in builder) |

---

## Data Model

```
Automation
  id, name, description
  is_active
  cron_expression
  schedule_preset
  trigger_conditions: TriggerCondition[]
  workflow_graph: { blocks: WorkflowBlock[], edges: WorkflowEdge[] }
  source_conversation_id, source_message_id
  created_at, updated_at

AutomationRun
  id, automation_id
  started_at, completed_at
  status: "success" | "error" | "skipped"
  triggered: bool          ← true if conditions were met
  result_snapshot          ← endpoint block output
  error_message

Notification
  id, automation_id, run_id
  created_at
  message
  is_read
```

---

## Current Limitations

- SQL queries are read-only (SELECT / WITH / EXPLAIN only)
- Trigger condition evaluation happens server-side in `automations/scheduler.py`
- Notifications are stored in the DB but not yet pushed via WebSocket (polling required)
- Test Run is only available when editing a saved automation (not during initial creation)
- The SQL editor in the workflow builder saves changes to the local store; they are persisted when you click "Update Automation"
