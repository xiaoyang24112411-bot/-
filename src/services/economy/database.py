"""SQLite connection, schema migration, and transaction helpers."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from src.config import get_economy_settings

SCHEMA_VERSION = 6

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS economy_accounts (
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
    total_earned INTEGER NOT NULL DEFAULT 0 CHECK (total_earned >= 0),
    total_spent INTEGER NOT NULL DEFAULT 0 CHECK (total_spent >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS daily_checkins (
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    checkin_date TEXT NOT NULL,
    reward INTEGER NOT NULL CHECK (reward > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id, checkin_date),
    FOREIGN KEY (group_id, user_id)
        REFERENCES economy_accounts(group_id, user_id)
);

CREATE TABLE IF NOT EXISTS point_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    change_amount INTEGER NOT NULL CHECK (change_amount != 0),
    balance_after INTEGER NOT NULL CHECK (balance_after >= 0),
    event_type TEXT NOT NULL,
    reference_id TEXT NOT NULL,
    counterparty_user_id INTEGER,
    note TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (group_id, user_id, event_type, reference_id),
    FOREIGN KEY (group_id, user_id)
        REFERENCES economy_accounts(group_id, user_id)
);

CREATE TABLE IF NOT EXISTS point_transfers (
    id TEXT PRIMARY KEY,
    group_id INTEGER NOT NULL,
    sender_user_id INTEGER NOT NULL,
    receiver_user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL CHECK (amount > 0),
    request_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    CHECK (sender_user_id != receiver_user_id)
);

CREATE TABLE IF NOT EXISTS red_packets (
    id TEXT PRIMARY KEY,
    group_id INTEGER NOT NULL,
    sender_user_id INTEGER NOT NULL,
    total_amount INTEGER NOT NULL CHECK (total_amount > 0),
    total_count INTEGER NOT NULL CHECK (total_count > 0),
    remaining_amount INTEGER NOT NULL CHECK (remaining_amount >= 0),
    remaining_count INTEGER NOT NULL CHECK (remaining_count >= 0),
    status TEXT NOT NULL CHECK (status IN ('open', 'exhausted', 'expired', 'refunded')),
    request_id TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    refunded_at TEXT,
    created_at TEXT NOT NULL,
    CHECK (total_amount >= total_count),
    CHECK (remaining_amount <= total_amount),
    CHECK (remaining_count <= total_count)
);

CREATE TABLE IF NOT EXISTS red_packet_claims (
    packet_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL CHECK (amount > 0),
    request_id TEXT NOT NULL UNIQUE,
    claimed_at TEXT NOT NULL,
    PRIMARY KEY (packet_id, user_id),
    FOREIGN KEY (packet_id) REFERENCES red_packets(id)
);

CREATE TABLE IF NOT EXISTS robbery_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    result_code TEXT NOT NULL CHECK (result_code IN ('success', 'loss', 'miss')),
    change_amount INTEGER NOT NULL,
    balance_before INTEGER NOT NULL CHECK (balance_before >= 0),
    balance_after INTEGER NOT NULL CHECK (balance_after >= 0),
    request_id TEXT NOT NULL UNIQUE,
    played_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shop_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price INTEGER NOT NULL CHECK (price > 0),
    stock INTEGER CHECK (stock IS NULL OR stock >= 0),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (group_id, name)
);

CREATE TABLE IF NOT EXISTS shop_orders (
    id TEXT PRIMARY KEY,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    unit_price INTEGER NOT NULL CHECK (unit_price > 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    total_price INTEGER NOT NULL CHECK (total_price > 0),
    status TEXT NOT NULL CHECK (status IN ('pending', 'fulfilled', 'refunded')),
    request_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    fulfilled_at TEXT,
    fulfilled_by INTEGER,
    refunded_at TEXT,
    FOREIGN KEY (product_id) REFERENCES shop_products(id)
);

CREATE TABLE IF NOT EXISTS daily_spouses (
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    draw_date TEXT NOT NULL,
    spouse_user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id, draw_date)
);

CREATE TABLE IF NOT EXISTS daily_spouse_forces (
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    draw_date TEXT NOT NULL,
    target_user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id, draw_date)
);

CREATE TABLE IF NOT EXISTS daily_fortunes (
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    fortune_date TEXT NOT NULL,
    fortune_level TEXT NOT NULL,
    score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 100),
    summary TEXT NOT NULL,
    lucky_color TEXT NOT NULL,
    lucky_number INTEGER NOT NULL CHECK (lucky_number BETWEEN 0 AND 99),
    lucky_direction TEXT NOT NULL,
    lucky_item TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id, fortune_date)
);

CREATE TABLE IF NOT EXISTS gomoku_games (
    group_id INTEGER PRIMARY KEY,
    game_id TEXT NOT NULL UNIQUE,
    black_user_id INTEGER NOT NULL,
    white_user_id INTEGER,
    status TEXT NOT NULL CHECK (
        status IN ('waiting', 'playing', 'black_won', 'white_won', 'draw', 'aborted')
    ),
    current_user_id INTEGER,
    board_json TEXT NOT NULL DEFAULT '[]',
    winner_user_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cultivation_profiles (
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    realm_index INTEGER NOT NULL DEFAULT 0 CHECK (realm_index >= 0),
    cultivation INTEGER NOT NULL DEFAULT 0 CHECK (cultivation >= 0),
    spirit_stones INTEGER NOT NULL DEFAULT 0 CHECK (spirit_stones >= 0),
    last_cultivated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS cultivation_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('cultivate', 'breakthrough')),
    cultivation_gain INTEGER NOT NULL DEFAULT 0,
    spirit_stone_gain INTEGER NOT NULL DEFAULT 0,
    request_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    FOREIGN KEY (group_id, user_id)
        REFERENCES cultivation_profiles(group_id, user_id)
);

CREATE TABLE IF NOT EXISTS roulette_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    wager INTEGER NOT NULL CHECK (wager >= 5),
    chamber INTEGER NOT NULL CHECK (chamber BETWEEN 1 AND 6),
    result_code TEXT NOT NULL CHECK (result_code IN ('safe', 'hit')),
    change_amount INTEGER NOT NULL,
    balance_before INTEGER NOT NULL CHECK (balance_before >= 0),
    balance_after INTEGER NOT NULL CHECK (balance_after >= 0),
    request_id TEXT NOT NULL UNIQUE,
    played_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS yugioh_card_cache (
    query_key TEXT PRIMARY KEY,
    response_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_personas (
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    persona TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS wordcloud_group_settings (
    group_id INTEGER PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    retention_days INTEGER NOT NULL DEFAULT 30 CHECK (retention_days BETWEEN 1 AND 90),
    updated_by INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wordcloud_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    message_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_checkins_group_date
    ON daily_checkins(group_id, checkin_date);
CREATE INDEX IF NOT EXISTS idx_transactions_account_time
    ON point_transactions(group_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_red_packets_group_status_time
    ON red_packets(group_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_robbery_cooldown
    ON robbery_records(group_id, user_id, played_at DESC);
CREATE INDEX IF NOT EXISTS idx_products_group_enabled
    ON shop_products(group_id, enabled, id);
CREATE INDEX IF NOT EXISTS idx_orders_group_status
    ON shop_orders(group_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_daily_spouses_group_date
    ON daily_spouses(group_id, draw_date);
CREATE INDEX IF NOT EXISTS idx_daily_spouse_forces_group_date
    ON daily_spouse_forces(group_id, draw_date);
CREATE INDEX IF NOT EXISTS idx_daily_fortunes_group_date
    ON daily_fortunes(group_id, fortune_date);
CREATE INDEX IF NOT EXISTS idx_cultivation_actions_user_time
    ON cultivation_actions(group_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_roulette_user_time
    ON roulette_records(group_id, user_id, played_at DESC);
CREATE INDEX IF NOT EXISTS idx_wordcloud_messages_group_time
    ON wordcloud_messages(group_id, created_at DESC);
"""


class EconomyDatabase:
    """Own one database path and open short-lived concurrency-safe connections."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._initialized = False
        self._initialize_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._initialize_lock:
            if self._initialized:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self.path) as connection:
                await connection.execute("PRAGMA journal_mode = WAL")
                await connection.execute("PRAGMA foreign_keys = ON")
                await connection.execute("PRAGMA busy_timeout = 5000")
                await connection.executescript(SCHEMA_SQL)
                await connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) "
                    "VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                    (SCHEMA_VERSION,),
                )
                await connection.commit()
            self._initialized = True

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        await self.initialize()
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        await connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            await connection.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        async with self.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                await connection.rollback()
                raise
            else:
                await connection.commit()


_database: EconomyDatabase | None = None


def get_economy_database() -> EconomyDatabase:
    global _database
    if _database is None:
        _database = EconomyDatabase(get_economy_settings().database_path)
    return _database
