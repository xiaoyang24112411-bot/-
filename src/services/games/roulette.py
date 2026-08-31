"""Point-backed Russian roulette settlement."""

import random
from dataclasses import dataclass
from datetime import UTC, datetime

from src.services.economy.common import (
    account_balance,
    apply_change,
    ensure_account,
    iso_time,
)
from src.services.economy.database import EconomyDatabase
from src.services.economy.errors import EconomyError


@dataclass(frozen=True)
class RouletteResult:
    result_code: str
    chamber: int
    wager: int
    change_amount: int
    balance: int


async def play_roulette(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    wager: int,
    request_id: str,
    cooldown_seconds: int,
    max_wager: int,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> RouletteResult:
    if wager < 5:
        raise EconomyError("每次至少投入 5 积分。")
    if wager > max_wager:
        raise EconomyError(f"单次最多投入 {max_wager} 积分。")

    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)
    timestamp = iso_time(current)
    generator = rng or random.SystemRandom()

    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT 1 FROM roulette_records WHERE request_id = ?", (request_id,)
        )
        if await cursor.fetchone() is not None:
            raise EconomyError("这次轮盘请求已经处理过了。")

        await ensure_account(connection, group_id, user_id, timestamp)
        balance_before = await account_balance(connection, group_id, user_id)
        if balance_before < wager:
            raise EconomyError("积分不足，无法参加轮盘。")

        cursor = await connection.execute(
            "SELECT played_at FROM roulette_records "
            "WHERE group_id = ? AND user_id = ? ORDER BY played_at DESC LIMIT 1",
            (group_id, user_id),
        )
        latest = await cursor.fetchone()
        if latest is not None and cooldown_seconds > 0:
            elapsed = (current - datetime.fromisoformat(latest["played_at"])).total_seconds()
            if elapsed < cooldown_seconds:
                remaining = max(1, int(cooldown_seconds - elapsed + 0.999))
                raise EconomyError(f"轮盘冷却中，请 {remaining} 秒后再试。")

        chamber = generator.randint(1, 6)
        result_code = "hit" if chamber == 1 else "safe"
        change_amount = -wager if result_code == "hit" else max(1, wager // 5)
        balance_after = await apply_change(
            connection,
            group_id=group_id,
            user_id=user_id,
            amount=change_amount,
            event_type="roulette",
            reference_id=request_id,
            note="俄罗斯轮盘",
            now=timestamp,
        )
        await connection.execute(
            "INSERT INTO roulette_records"
            "(group_id, user_id, wager, chamber, result_code, change_amount, "
            "balance_before, balance_after, request_id, played_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                group_id,
                user_id,
                wager,
                chamber,
                result_code,
                change_amount,
                balance_before,
                balance_after,
                request_id,
                timestamp,
            ),
        )

    return RouletteResult(result_code, chamber, wager, change_amount, balance_after)
