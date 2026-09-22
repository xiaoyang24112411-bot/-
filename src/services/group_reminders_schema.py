"""Additive schema for one-shot, account-scoped group reminders."""

GROUP_REMINDERS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS group_reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    request_id TEXT NOT NULL,
    body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 500),
    due_at INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'claimed', 'sending', 'sent', 'failed', 'cancelled', 'expired')
    ),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE (bot_id, group_id, request_id)
);
CREATE INDEX IF NOT EXISTS idx_group_reminders_due
    ON group_reminders(bot_id, status, due_at, id);
CREATE INDEX IF NOT EXISTS idx_group_reminders_owner
    ON group_reminders(bot_id, group_id, user_id, status);
CREATE INDEX IF NOT EXISTS idx_group_reminders_cleanup
    ON group_reminders(status, updated_at);
"""
