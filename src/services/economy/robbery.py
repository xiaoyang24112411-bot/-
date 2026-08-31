"""Cooldown-based random gain/loss mini-game."""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from .common import account_balance, apply_change, ensure_account, iso_time, utc_now
from .database import EconomyDatabase
from .errors import EconomyError


@dataclass(frozen=True)
class RobberyResult:
    result_code: str
    change_amount: int
    balance: int


async def play_robbery(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    request_id: str,
    cooldown_seconds: int,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> RobberyResult:
    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=utc_now().tzinfo)
    timestamp = iso_time(current)
    generator = rng or random.SystemRandom()

    async with database.transaction() as connection:
        duplicate_cursor = await connection.execute(
            "SELECT 1 FROM robbery_records WHERE request_id = ?",
            (request_id,),
        )
        if await duplicate_cursor.fetchone() is not None:
            raise EconomyError("这次打劫已经处理过了。")
        cursor = await connection.execute(
            "SELECT played_at FROM robbery_records WHERE group_id = ? AND user_id = ? "
            "ORDER BY played_at DESC LIMIT 1",
            (group_id, user_id),
        )
        previous = await cursor.fetchone()
        if previous is not None:
            previous_time = datetime.fromisoformat(previous["played_at"])
            remaining = timedelta(seconds=cooldown_seconds) - (current - previous_time)
            if remaining.total_seconds() > 0:
                minutes = max(1, int((remaining.total_seconds() + 59) // 60))
                raise EconomyError(f"打劫冷却中，请约 {minutes} 分钟后再试。")

        await ensure_account(connection, group_id, user_id, timestamp)
        balance_before = await account_balance(connection, group_id, user_id)
        roll = generator.random()
        if roll < 0.55:
            result_code = "success"
            change = generator.randint(5, 30)
        elif roll < 0.90:
            result_code = "loss"
            change = -min(balance_before, generator.randint(1, 20))
        else:
            result_code = "miss"
            change = 0

        record_cursor = await connection.execute(
            "INSERT INTO robbery_records"
            "(group_id, user_id, result_code, change_amount, balance_before, balance_after, "
            "request_id, played_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                group_id,
                user_id,
                result_code,
                change,
                balance_before,
                balance_before + change,
                request_id,
                timestamp,
            ),
        )
        record_id = str(record_cursor.lastrowid)
        if change:
            balance_after = await apply_change(
                connection,
                group_id=group_id,
                user_id=user_id,
                amount=change,
                event_type="robbery",
                reference_id=record_id,
                note="积分打劫小游戏",
                now=timestamp,
            )
        else:
            balance_after = balance_before
    return RobberyResult(result_code, change, balance_after)
