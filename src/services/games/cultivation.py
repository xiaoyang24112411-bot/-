"""Persistent lightweight text cultivation game."""

import random
from dataclasses import dataclass
from datetime import UTC, datetime

from src.services.economy.common import iso_time
from src.services.economy.database import EconomyDatabase
from src.services.economy.errors import EconomyError

REALMS = (
    ("炼气", 0),
    ("筑基", 100),
    ("金丹", 300),
    ("元婴", 700),
    ("化神", 1500),
    ("炼虚", 3000),
    ("合体", 6000),
    ("大乘", 10000),
    ("渡劫", 20000),
)


@dataclass(frozen=True)
class CultivationProfile:
    realm_index: int
    realm_name: str
    cultivation: int
    spirit_stones: int
    next_realm_name: str | None
    next_requirement: int | None


@dataclass(frozen=True)
class CultivateResult:
    profile: CultivationProfile
    cultivation_gain: int
    spirit_stone_gain: int


def _profile_from_row(row) -> CultivationProfile:
    realm_index = int(row["realm_index"])
    next_index = realm_index + 1
    return CultivationProfile(
        realm_index=realm_index,
        realm_name=REALMS[realm_index][0],
        cultivation=int(row["cultivation"]),
        spirit_stones=int(row["spirit_stones"]),
        next_realm_name=REALMS[next_index][0] if next_index < len(REALMS) else None,
        next_requirement=REALMS[next_index][1] if next_index < len(REALMS) else None,
    )


async def _ensure_profile(connection, group_id: int, user_id: int, now: str) -> None:
    await connection.execute(
        "INSERT OR IGNORE INTO cultivation_profiles"
        "(group_id, user_id, realm_index, cultivation, spirit_stones, created_at, updated_at) "
        "VALUES (?, ?, 0, 0, 10, ?, ?)",
        (group_id, user_id, now, now),
    )


async def get_cultivation_profile(
    database: EconomyDatabase,
    group_id: int,
    user_id: int,
) -> CultivationProfile:
    timestamp = iso_time()
    async with database.transaction() as connection:
        await _ensure_profile(connection, group_id, user_id, timestamp)
        cursor = await connection.execute(
            "SELECT * FROM cultivation_profiles WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        )
        return _profile_from_row(await cursor.fetchone())


async def cultivate(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    request_id: str,
    cooldown_seconds: int,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> CultivateResult:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)
    timestamp = iso_time(current)
    generator = rng or random.SystemRandom()

    async with database.transaction() as connection:
        await _ensure_profile(connection, group_id, user_id, timestamp)
        cursor = await connection.execute(
            "SELECT * FROM cultivation_profiles WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        )
        profile_row = await cursor.fetchone()
        if profile_row["last_cultivated_at"] and cooldown_seconds > 0:
            last_time = datetime.fromisoformat(profile_row["last_cultivated_at"])
            elapsed = (current - last_time).total_seconds()
            if elapsed < cooldown_seconds:
                remaining = max(1, int(cooldown_seconds - elapsed + 0.999))
                raise EconomyError(f"灵气尚未恢复，请 {remaining} 秒后再修炼。")

        cursor = await connection.execute(
            "SELECT 1 FROM cultivation_actions WHERE request_id = ?", (request_id,)
        )
        if await cursor.fetchone() is not None:
            raise EconomyError("这次修炼已经处理过了。")

        cultivation_gain = generator.randint(15, 35)
        stone_gain = generator.randint(1, 5)
        await connection.execute(
            "UPDATE cultivation_profiles SET cultivation = cultivation + ?, "
            "spirit_stones = spirit_stones + ?, last_cultivated_at = ?, updated_at = ? "
            "WHERE group_id = ? AND user_id = ?",
            (cultivation_gain, stone_gain, timestamp, timestamp, group_id, user_id),
        )
        await connection.execute(
            "INSERT INTO cultivation_actions"
            "(group_id, user_id, action_type, cultivation_gain, spirit_stone_gain, "
            "request_id, created_at) VALUES (?, ?, 'cultivate', ?, ?, ?, ?)",
            (group_id, user_id, cultivation_gain, stone_gain, request_id, timestamp),
        )
        cursor = await connection.execute(
            "SELECT * FROM cultivation_profiles WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        )
        result_profile = _profile_from_row(await cursor.fetchone())

    return CultivateResult(result_profile, cultivation_gain, stone_gain)


async def breakthrough(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    request_id: str,
) -> CultivationProfile:
    timestamp = iso_time()
    async with database.transaction() as connection:
        await _ensure_profile(connection, group_id, user_id, timestamp)
        cursor = await connection.execute(
            "SELECT 1 FROM cultivation_actions WHERE request_id = ?", (request_id,)
        )
        if await cursor.fetchone() is not None:
            raise EconomyError("这次突破已经处理过了。")

        cursor = await connection.execute(
            "SELECT * FROM cultivation_profiles WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        )
        row = await cursor.fetchone()
        realm_index = int(row["realm_index"])
        next_index = realm_index + 1
        if next_index >= len(REALMS):
            raise EconomyError("你已经达到当前版本的最高境界。")
        requirement = REALMS[next_index][1]
        if int(row["cultivation"]) < requirement:
            needed = requirement - int(row["cultivation"])
            raise EconomyError(f"修为不足，距离 {REALMS[next_index][0]} 还差 {needed}。")

        await connection.execute(
            "UPDATE cultivation_profiles SET realm_index = ?, updated_at = ? "
            "WHERE group_id = ? AND user_id = ?",
            (next_index, timestamp, group_id, user_id),
        )
        await connection.execute(
            "INSERT INTO cultivation_actions"
            "(group_id, user_id, action_type, request_id, created_at) "
            "VALUES (?, ?, 'breakthrough', ?, ?)",
            (group_id, user_id, request_id, timestamp),
        )
        cursor = await connection.execute(
            "SELECT * FROM cultivation_profiles WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        )
        return _profile_from_row(await cursor.fetchone())
