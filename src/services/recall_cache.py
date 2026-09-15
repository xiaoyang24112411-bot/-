"""Opt-in, memory-only cache for recently recalled group text messages."""

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone

from src.services.economy.common import iso_time
from src.services.economy.database import EconomyDatabase


@dataclass(frozen=True)
class CachedMessage:
    message_id: int
    user_id: int
    text: str
    sent_at: int


@dataclass(frozen=True)
class RecalledMessage:
    user_id: int
    operator_id: int
    text: str
    recalled_at: str


_observed: dict[int, deque[CachedMessage]] = defaultdict(lambda: deque(maxlen=500))
_recalled: dict[int, deque[RecalledMessage]] = defaultdict(lambda: deque(maxlen=20))
_enabled: dict[int, bool] = {}


async def is_recall_enabled(database: EconomyDatabase, group_id: int) -> bool:
    if group_id in _enabled:
        return _enabled[group_id]
    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT enabled FROM recall_group_settings WHERE group_id = ?", (group_id,)
        )
        row = await cursor.fetchone()
    enabled = bool(row["enabled"]) if row else False
    _enabled[group_id] = enabled
    return enabled


async def set_recall_enabled(
    database: EconomyDatabase, group_id: int, enabled: bool, updated_by: int
) -> None:
    now = iso_time()
    async with database.transaction() as connection:
        await connection.execute(
            "INSERT INTO recall_group_settings(group_id, enabled, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(group_id) DO UPDATE SET "
            "enabled = excluded.enabled, updated_by = excluded.updated_by, "
            "updated_at = excluded.updated_at",
            (group_id, int(enabled), updated_by, now),
        )
    _enabled[group_id] = enabled
    if not enabled:
        _observed.pop(group_id, None)
        _recalled.pop(group_id, None)


def remember_message(group_id: int, message: CachedMessage) -> None:
    if message.text.strip():
        _observed[group_id].append(message)


def remember_recall(group_id: int, message_id: int, operator_id: int) -> bool:
    messages = _observed[group_id]
    source = next((item for item in reversed(messages) if item.message_id == message_id), None)
    if source is None:
        return False
    _recalled[group_id].append(
        RecalledMessage(
            user_id=source.user_id,
            operator_id=operator_id,
            text=source.text,
            recalled_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    return True


def latest_recalled(group_id: int) -> RecalledMessage | None:
    records = _recalled[group_id]
    return records[-1] if records else None

