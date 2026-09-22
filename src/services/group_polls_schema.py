"""Additive schema for group polls; applied by the shared database initializer."""

GROUP_POLLS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS group_polls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    creator_user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    options_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    request_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    closed_at TEXT,
    UNIQUE (bot_id, group_id, id),
    UNIQUE (bot_id, group_id, request_id)
);
CREATE TABLE IF NOT EXISTS group_poll_votes (
    bot_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    poll_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    option_number INTEGER NOT NULL CHECK (option_number BETWEEN 1 AND 10),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (bot_id, group_id, poll_id, user_id),
    FOREIGN KEY (bot_id, group_id, poll_id)
        REFERENCES group_polls(bot_id, group_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_group_polls_active
    ON group_polls(bot_id, group_id, status, id DESC);
"""
