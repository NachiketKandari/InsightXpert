"""Schema migration constants: columns and indexes applied idempotently at startup."""

# Migration columns: (table, column, column_def).
MIGRATION_COLUMNS = [
    ("users", "is_admin", "BOOLEAN DEFAULT 0 NOT NULL"),
    ("users", "last_active", "DATETIME"),
    ("users", "org_id", "VARCHAR(100)"),
    ("users", "updated_at", "DATETIME"),
    ("conversations", "is_starred", "BOOLEAN DEFAULT 0 NOT NULL"),
    ("conversations", "org_id", "VARCHAR(100)"),
    ("messages", "feedback", "BOOLEAN"),
    ("messages", "feedback_comment", "TEXT"),
    ("messages", "input_tokens", "INTEGER"),
    ("messages", "output_tokens", "INTEGER"),
    ("messages", "generation_time_ms", "INTEGER"),
    ("automations", "workflow_json", "TEXT"),
    ("datasets", "organization_id", "VARCHAR(100)"),
]

# All indexes and unique constraints that must exist on every database.
SCHEMA_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_conversations_updated_at ON conversations (updated_at)",
    "CREATE INDEX IF NOT EXISTS ix_conversations_org_id ON conversations (org_id)",
    "CREATE INDEX IF NOT EXISTS ix_messages_conversation_id ON messages (conversation_id)",
    "CREATE INDEX IF NOT EXISTS ix_messages_created_at ON messages (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_messages_conv_created ON messages (conversation_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_automation_runs_automation_id ON automation_runs (automation_id)",
    "CREATE INDEX IF NOT EXISTS ix_automation_runs_auto_created ON automation_runs (automation_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_automations_active_next_run ON automations (is_active, next_run_at)",
    "CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_notifications_user_read ON notifications (user_id, is_read, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_dataset_stats_stat_group ON dataset_stats (stat_group)",
    "CREATE INDEX IF NOT EXISTS ix_dataset_stats_group_dim ON dataset_stats (stat_group, dimension)",
    "CREATE INDEX IF NOT EXISTS ix_datasets_organization_id ON datasets (organization_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_dataset_columns_ds_col ON dataset_columns (dataset_id, column_name)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_example_queries_ds_question ON example_queries (dataset_id, question)",
    "CREATE INDEX IF NOT EXISTS ix_automation_triggers_auto_id ON automation_triggers (automation_id)",
    "CREATE INDEX IF NOT EXISTS ix_trigger_templates_created_by ON trigger_templates (created_by)",
    "CREATE INDEX IF NOT EXISTS ix_enrichment_traces_message ON enrichment_traces (message_id)",
]
