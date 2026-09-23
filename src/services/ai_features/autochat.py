"""Persistent auto-chat switches and short-lived in-memory group context."""

import random
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.config import AutoChatSettings
from src.services.economy.common import iso_time
from src.services.economy.database import EconomyDatabase


@dataclass(frozen=True)
class AutoChatState:
    enabled: bool
    updated_by: int | None


@dataclass(frozen=True)
class PeakAutochatState:
    # None means the controller has not overridden the environment default.
    allow_during_peak: bool | None
    updated_by: int | None


@dataclass(frozen=True)
class ChatLine:
    user_id: int
    display_name: str
    text: str
    created_at: datetime


class RecentChatBuffer:
    """Keep bounded context in RAM; chat content is never written to SQLite."""

    def __init__(self, maximum_messages: int = 30) -> None:
        self._lines: dict[int, deque[ChatLine]] = defaultdict(
            lambda: deque(maxlen=maximum_messages)
        )

    def append(
        self,
        group_id: int,
        user_id: int,
        display_name: str,
        text: str,
        *,
        now: datetime | None = None,
    ) -> None:
        value = " ".join(text.split()).strip()[:300]
        if not value:
            return
        self._lines[group_id].append(
            ChatLine(
                user_id=user_id,
                display_name=" ".join(display_name.split()).strip()[:40] or str(user_id),
                text=value,
                created_at=now or datetime.now(timezone.utc),
            )
        )

    def recent(
        self,
        group_id: int,
        *,
        limit: int,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> tuple[ChatLine, ...]:
        current = now or datetime.now(timezone.utc)
        cutoff = current - timedelta(seconds=ttl_seconds)
        # Also evict inactive groups: filtering only the requested group's result
        # would retain old conversation text in memory indefinitely.
        for stored_group, lines in tuple(self._lines.items()):
            remaining = deque(
                (line for line in lines if line.created_at >= cutoff), maxlen=lines.maxlen
            )
            if remaining:
                self._lines[stored_group] = remaining
            else:
                del self._lines[stored_group]
        if limit <= 0:
            return ()
        return tuple(self._lines.get(group_id, ()))[-limit:]

    def clear(self, group_id: int) -> None:
        self._lines.pop(group_id, None)


async def get_autochat_state(database: EconomyDatabase, group_id: int) -> AutoChatState:
    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT enabled, updated_by FROM ai_autochat_settings WHERE group_id = ?",
            (group_id,),
        )
        row = await cursor.fetchone()
    if not row:
        return AutoChatState(False, None)
    return AutoChatState(bool(row["enabled"]), int(row["updated_by"]))


async def set_autochat_enabled(
    database: EconomyDatabase,
    group_id: int,
    enabled: bool,
    updated_by: int,
) -> AutoChatState:
    now = iso_time()
    async with database.transaction() as connection:
        await connection.execute(
            "INSERT INTO ai_autochat_settings"
            "(group_id, enabled, updated_by, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(group_id) DO UPDATE SET enabled = excluded.enabled, "
            "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            (group_id, int(enabled), updated_by, now),
        )
    return await get_autochat_state(database, group_id)


async def get_peak_autochat_state(
    database: EconomyDatabase, group_id: int
) -> PeakAutochatState:
    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT allow_during_peak, updated_by FROM ai_autochat_peak_settings "
            "WHERE group_id = ?",
            (group_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return PeakAutochatState(None, None)
    return PeakAutochatState(bool(row["allow_during_peak"]), int(row["updated_by"]))


async def set_peak_autochat_enabled(
    database: EconomyDatabase, group_id: int, allow_during_peak: bool, updated_by: int
) -> PeakAutochatState:
    async with database.transaction() as connection:
        await connection.execute(
            "INSERT INTO ai_autochat_peak_settings"
            "(group_id, allow_during_peak, updated_by, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(group_id) DO UPDATE SET "
            "allow_during_peak = excluded.allow_during_peak, "
            "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            (group_id, int(allow_during_peak), updated_by, iso_time()),
        )
    return PeakAutochatState(allow_during_peak, updated_by)


def in_quiet_hours(hour: int, start_hour: int, end_hour: int) -> bool:
    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def should_sample_reply(
    lines: tuple[ChatLine, ...],
    settings: AutoChatSettings,
    *,
    china_hour: int,
    bot_id: int | None = None,
    random_value: Callable[[], float] = random.random,
) -> bool:
    if in_quiet_hours(china_hour, settings.quiet_start_hour, settings.quiet_end_hour):
        return False
    human_lines = tuple(line for line in lines if line.user_id != bot_id)
    if not lines or len(human_lines) < settings.minimum_messages:
        return False
    if len({line.user_id for line in human_lines}) < 2:
        return False
    latest = lines[-1].text
    if latest.startswith(("/", "#")) or len(latest) > 300:
        return False
    chance = settings.trigger_percent
    if latest.endswith(("?", "？", "吗", "呢")):
        chance = min(100, chance * 2)
    return random_value() < chance / 100


def format_context(lines: tuple[ChatLine, ...]) -> str:
    return "\n".join(
        f"{line.display_name}（QQ {line.user_id}）：{line.text}" for line in lines
    )
