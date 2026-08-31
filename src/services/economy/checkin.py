"""Daily check-in business logic."""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .common import apply_change, ensure_account, iso_time
from .database import EconomyDatabase
from .errors import EconomyError

BEIJING = timezone(timedelta(hours=8), "Asia/Shanghai")


@dataclass(frozen=True)
class CheckinResult:
    reward: int
    balance: int
    checkin_date: str


async def check_in(
    database: EconomyDatabase,
    group_id: int,
    user_id: int,
    reward_min: int,
    reward_max: int,
    *,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> CheckinResult:
    if reward_min <= 0 or reward_max < reward_min:
        raise ValueError("invalid check-in reward range")

    current = now or datetime.now(BEIJING)
    if current.tzinfo is None:
        current = current.replace(tzinfo=BEIJING)
    current = current.astimezone(BEIJING)
    date_text = current.date().isoformat()
    timestamp = iso_time(current)
    generator = rng or random.SystemRandom()

    async with database.transaction() as connection:
        await ensure_account(connection, group_id, user_id, timestamp)
        cursor = await connection.execute(
            "SELECT reward FROM daily_checkins "
            "WHERE group_id = ? AND user_id = ? AND checkin_date = ?",
            (group_id, user_id, date_text),
        )
        if await cursor.fetchone() is not None:
            raise EconomyError("今天已经签到过啦，明天再来吧。")

        reward = generator.randint(reward_min, reward_max)
        await connection.execute(
            "INSERT INTO daily_checkins(group_id, user_id, checkin_date, reward, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (group_id, user_id, date_text, reward, timestamp),
        )
        balance = await apply_change(
            connection,
            group_id=group_id,
            user_id=user_id,
            amount=reward,
            event_type="checkin",
            reference_id=f"{group_id}:{user_id}:{date_text}",
            note="每日签到",
            now=timestamp,
        )
    return CheckinResult(reward, balance, date_text)
