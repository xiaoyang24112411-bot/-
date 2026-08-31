"""Persisted daily random-spouse draws."""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.services.economy.common import iso_time
from src.services.economy.database import EconomyDatabase
from src.services.economy.errors import EconomyError

BEIJING = timezone(timedelta(hours=8), "Asia/Shanghai")


@dataclass(frozen=True)
class SpouseCandidate:
    user_id: int
    display_name: str = ""


@dataclass(frozen=True)
class DailySpouseResult:
    spouse_user_id: int
    spouse_name: str
    draw_date: str
    is_new: bool


def _beijing_date(now: datetime | None) -> tuple[str, str]:
    current = now or datetime.now(BEIJING)
    if current.tzinfo is None:
        current = current.replace(tzinfo=BEIJING)
    current = current.astimezone(BEIJING)
    return current.date().isoformat(), iso_time(current)


async def draw_daily_spouse(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    candidates: list[SpouseCandidate],
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> DailySpouseResult:
    """Return today's stored draw, creating it atomically when needed."""
    if not candidates:
        raise EconomyError("没有找到可以抽取的群成员。")

    unique_candidates = {candidate.user_id: candidate for candidate in candidates}
    date_text, timestamp = _beijing_date(now)

    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT spouse_user_id FROM daily_spouses "
            "WHERE group_id = ? AND user_id = ? AND draw_date = ?",
            (group_id, user_id, date_text),
        )
        row = await cursor.fetchone()
        if row is not None:
            spouse_id = int(row["spouse_user_id"])
            stored = unique_candidates.get(spouse_id)
            return DailySpouseResult(
                spouse_user_id=spouse_id,
                spouse_name=stored.display_name if stored else "",
                draw_date=date_text,
                is_new=False,
            )

        generator = rng or random.SystemRandom()
        spouse = generator.choice(list(unique_candidates.values()))
        await connection.execute(
            "INSERT INTO daily_spouses"
            "(group_id, user_id, draw_date, spouse_user_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (group_id, user_id, date_text, spouse.user_id, timestamp),
        )

    return DailySpouseResult(
        spouse_user_id=spouse.user_id,
        spouse_name=spouse.display_name,
        draw_date=date_text,
        is_new=True,
    )


async def force_daily_spouse(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    target: SpouseCandidate,
    now: datetime | None = None,
) -> DailySpouseResult:
    """Replace today's draw once with a specifically mentioned group member."""
    if target.user_id == user_id:
        raise EconomyError("不能强娶自己，请 @ 另一位群友。")

    date_text, timestamp = _beijing_date(now)
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT 1 FROM daily_spouse_forces "
            "WHERE group_id = ? AND user_id = ? AND draw_date = ?",
            (group_id, user_id, date_text),
        )
        if await cursor.fetchone() is not None:
            raise EconomyError("今天已经强娶过了，明天再来吧。")

        await connection.execute(
            "INSERT INTO daily_spouse_forces"
            "(group_id, user_id, draw_date, target_user_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (group_id, user_id, date_text, target.user_id, timestamp),
        )
        await connection.execute(
            "INSERT INTO daily_spouses"
            "(group_id, user_id, draw_date, spouse_user_id, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(group_id, user_id, draw_date) DO UPDATE SET "
            "spouse_user_id = excluded.spouse_user_id, created_at = excluded.created_at",
            (group_id, user_id, date_text, target.user_id, timestamp),
        )

    return DailySpouseResult(
        spouse_user_id=target.user_id,
        spouse_name=target.display_name,
        draw_date=date_text,
        is_new=True,
    )
