"""One-to-one, group-scoped daily spouse bindings with a mutual release path."""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import aiosqlite

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


@dataclass(frozen=True)
class SpouseUnlinkResult:
    partner_user_id: int
    was_mutual_binding: bool


def _beijing_date(now: datetime | None) -> tuple[str, str]:
    current = now or datetime.now(BEIJING)
    if current.tzinfo is None:
        current = current.replace(tzinfo=BEIJING)
    current = current.astimezone(BEIJING)
    return current.date().isoformat(), iso_time(current)


async def _partner(
    connection: aiosqlite.Connection, group_id: int, draw_date: str, user_id: int
) -> int | None:
    cursor = await connection.execute(
        "SELECT partner_user_id FROM daily_spouse_bindings "
        "WHERE group_id = ? AND draw_date = ? AND user_id = ?",
        (group_id, draw_date, user_id),
    )
    row = await cursor.fetchone()
    return int(row["partner_user_id"]) if row else None


async def _id_set(connection: aiosqlite.Connection, sql: str, params: tuple) -> set[int]:
    cursor = await connection.execute(sql, params)
    return {int(row["user_id"]) for row in await cursor.fetchall()}


async def _legacy_draw(
    connection: aiosqlite.Connection, group_id: int, draw_date: str, user_id: int
) -> int | None:
    cursor = await connection.execute(
        "SELECT spouse_user_id FROM daily_spouses "
        "WHERE group_id = ? AND draw_date = ? AND user_id = ?",
        (group_id, draw_date, user_id),
    )
    row = await cursor.fetchone()
    return int(row["spouse_user_id"]) if row else None


async def _was_released(
    connection: aiosqlite.Connection, group_id: int, draw_date: str, user_id: int
) -> bool:
    cursor = await connection.execute(
        "SELECT 1 FROM daily_spouse_releases "
        "WHERE group_id = ? AND draw_date = ? AND user_id = ?",
        (group_id, draw_date, user_id),
    )
    return await cursor.fetchone() is not None


async def _opted_out(connection: aiosqlite.Connection, group_id: int, user_id: int) -> bool:
    cursor = await connection.execute(
        "SELECT 1 FROM daily_spouse_optouts WHERE group_id = ? AND user_id = ?",
        (group_id, user_id),
    )
    return await cursor.fetchone() is not None


async def _bind(
    connection: aiosqlite.Connection,
    group_id: int,
    draw_date: str,
    user_id: int,
    partner_id: int,
    source: str,
    timestamp: str,
) -> None:
    # BEGIN IMMEDIATE serializes competing draws; both rows commit together.
    await connection.executemany(
        "INSERT INTO daily_spouse_bindings"
        "(group_id, draw_date, user_id, partner_user_id, source, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            (group_id, draw_date, user_id, partner_id, source, timestamp),
            (group_id, draw_date, partner_id, user_id, source, timestamp),
        ),
    )


async def _record_breakup(
    connection: aiosqlite.Connection,
    group_id: int,
    draw_date: str,
    user_id: int,
    partner_id: int,
    timestamp: str,
) -> None:
    lower, higher = sorted((user_id, partner_id))
    await connection.execute(
        "INSERT OR IGNORE INTO daily_spouse_breakups"
        "(group_id, draw_date, user_low_id, user_high_id, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (group_id, draw_date, lower, higher, timestamp),
    )


async def _release(
    connection: aiosqlite.Connection,
    group_id: int,
    draw_date: str,
    user_id: int,
    timestamp: str,
) -> SpouseUnlinkResult | None:
    partner_id = await _partner(connection, group_id, draw_date, user_id)
    if partner_id is not None:
        cursor = await connection.execute(
            "DELETE FROM daily_spouse_bindings WHERE group_id = ? AND draw_date = ? AND "
            "((user_id = ? AND partner_user_id = ?) OR "
            "(user_id = ? AND partner_user_id = ?))",
            (group_id, draw_date, user_id, partner_id, partner_id, user_id),
        )
        if cursor.rowcount != 2:
            raise EconomyError("绑定记录异常，请联系管理员检查数据。")
        await _record_breakup(connection, group_id, draw_date, user_id, partner_id, timestamp)
        for member_id in (user_id, partner_id):
            if await _legacy_draw(connection, group_id, draw_date, member_id) is not None:
                await connection.execute(
                    "INSERT OR IGNORE INTO daily_spouse_releases"
                    "(group_id, draw_date, user_id, created_at) VALUES (?, ?, ?, ?)",
                    (group_id, draw_date, member_id, timestamp),
                )
        return SpouseUnlinkResult(partner_id, True)

    # A schema-12 draw may not yet have been adopted into a mutual binding.
    legacy_id = await _legacy_draw(connection, group_id, draw_date, user_id)
    if legacy_id is None or await _was_released(connection, group_id, draw_date, user_id):
        return None
    await connection.execute(
        "INSERT INTO daily_spouse_releases"
        "(group_id, draw_date, user_id, created_at) VALUES (?, ?, ?, ?)",
        (group_id, draw_date, user_id, timestamp),
    )
    if legacy_id != user_id:
        await _record_breakup(connection, group_id, draw_date, user_id, legacy_id, timestamp)
    return SpouseUnlinkResult(legacy_id, False)


async def get_daily_spouse(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    candidates: list[SpouseCandidate] | None = None,
    now: datetime | None = None,
) -> DailySpouseResult | None:
    date_text, _ = _beijing_date(now)
    async with database.connect() as connection:
        partner_id = await _partner(connection, group_id, date_text, user_id)
    if partner_id is None:
        return None
    names = {candidate.user_id: candidate.display_name for candidate in candidates or []}
    return DailySpouseResult(partner_id, names.get(partner_id, ""), date_text, False)


async def draw_daily_spouse(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    candidates: list[SpouseCandidate],
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> DailySpouseResult:
    """Bind two free users for the day, or return either side's existing partner."""
    unique_candidates = {
        candidate.user_id: candidate
        for candidate in candidates
        if candidate.user_id > 0 and candidate.user_id != user_id
    }
    date_text, timestamp = _beijing_date(now)
    async with database.transaction() as connection:
        partner_id = await _partner(connection, group_id, date_text, user_id)
        if partner_id is not None:
            stored = unique_candidates.get(partner_id)
            return DailySpouseResult(
                partner_id, stored.display_name if stored else "", date_text, False
            )
        if await _opted_out(connection, group_id, user_id):
            raise EconomyError("你已退出本群老婆池，发送「加入老婆池」后再抽取。")
        if await _was_released(connection, group_id, date_text, user_id):
            raise EconomyError("今天的抽取已解绑，明天再抽；现在仍可强娶未绑定的群友。")

        reserved = await _id_set(
            connection,
            "SELECT user_id FROM daily_spouse_bindings WHERE group_id = ? AND draw_date = ?",
            (group_id, date_text),
        )
        reserved |= await _id_set(
            connection, "SELECT user_id FROM daily_spouse_optouts WHERE group_id = ?",
            (group_id,),
        )
        reserved |= await _id_set(connection, "SELECT user_id FROM bot_global_blacklist", ())
        # An unadopted pre-upgrade draw is a pending claim, not an available target.
        reserved |= await _id_set(
            connection,
            "SELECT user_id FROM daily_spouses AS old "
            "WHERE old.group_id = ? AND old.draw_date = ? AND "
            "NOT EXISTS (SELECT 1 FROM daily_spouse_releases AS released "
            "WHERE released.group_id = old.group_id AND "
            "released.draw_date = old.draw_date AND released.user_id = old.user_id)",
            (group_id, date_text),
        )
        cursor = await connection.execute(
            "SELECT user_low_id, user_high_id FROM daily_spouse_breakups "
            "WHERE group_id = ? AND draw_date = ? AND "
            "(user_low_id = ? OR user_high_id = ?)",
            (group_id, date_text, user_id, user_id),
        )
        former_partners = {
            int(row["user_high_id"] if row["user_low_id"] == user_id else row["user_low_id"])
            for row in await cursor.fetchall()
        }
        eligible = [candidate for candidate in unique_candidates.values()
                    if candidate.user_id not in reserved
                    and candidate.user_id not in former_partners]
        if not eligible:
            raise EconomyError("本群今天没有可配对的群友了，请稍后或明天再试。")

        legacy_id = await _legacy_draw(connection, group_id, date_text, user_id)
        spouse = unique_candidates.get(legacy_id) if legacy_id is not None else None
        if spouse not in eligible:
            spouse = (rng or random.SystemRandom()).choice(eligible)
        source = "legacy" if legacy_id == spouse.user_id else "random"
        await _bind(connection, group_id, date_text, user_id, spouse.user_id, source, timestamp)
        await connection.execute(
            "INSERT INTO daily_spouses"
            "(group_id, user_id, draw_date, spouse_user_id, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(group_id, user_id, draw_date) DO UPDATE SET "
            "spouse_user_id = excluded.spouse_user_id, created_at = excluded.created_at",
            (group_id, user_id, date_text, spouse.user_id, timestamp),
        )
    return DailySpouseResult(
        spouse.user_id, spouse.display_name, date_text, legacy_id != spouse.user_id
    )


async def force_daily_spouse(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    target: SpouseCandidate,
    now: datetime | None = None,
) -> DailySpouseResult:
    """Bind a chosen free target once per day; never overwrite either partner."""
    if target.user_id == user_id:
        raise EconomyError("不能强娶自己，请 @ 另一位群友。")
    date_text, timestamp = _beijing_date(now)
    async with database.transaction() as connection:
        if await _opted_out(connection, group_id, user_id):
            raise EconomyError("你已退出本群老婆池，请先发送「加入老婆池」。")
        if await _opted_out(connection, group_id, target.user_id):
            raise EconomyError("对方已退出本群老婆池，不能强娶。")
        blocked = await _id_set(connection, "SELECT user_id FROM bot_global_blacklist", ())
        if target.user_id in blocked:
            raise EconomyError("对方不可参与配对。")
        for member_id, label in ((user_id, "你"), (target.user_id, "对方")):
            if await _partner(connection, group_id, date_text, member_id) is not None:
                raise EconomyError(f"{label}今天已有绑定，请先由任意一方发送「解绑老婆」。")
            if (
                await _legacy_draw(connection, group_id, date_text, member_id) is not None
                and not await _was_released(connection, group_id, date_text, member_id)
            ):
                raise EconomyError(f"{label}今天已有抽取记录，请先发送「解绑老婆」。")
        cursor = await connection.execute(
            "SELECT 1 FROM daily_spouse_forces "
            "WHERE group_id = ? AND user_id = ? AND draw_date = ?",
            (group_id, user_id, date_text),
        )
        if await cursor.fetchone() is not None:
            raise EconomyError("今天已经强娶过了，明天再来吧。")

        await _bind(connection, group_id, date_text, user_id, target.user_id,
                    "forced", timestamp)
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
    return DailySpouseResult(target.user_id, target.display_name, date_text, True)


async def unlink_daily_spouse(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    now: datetime | None = None,
) -> SpouseUnlinkResult:
    """Either partner can release both sides; random draw stays spent today."""
    date_text, timestamp = _beijing_date(now)
    async with database.transaction() as connection:
        result = await _release(connection, group_id, date_text, user_id, timestamp)
        if result is None:
            raise EconomyError("你今天还没有绑定的群友老婆。")
        return result


async def set_spouse_pool_participation(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    participating: bool,
    now: datetime | None = None,
) -> tuple[bool, SpouseUnlinkResult | None]:
    """Let each member opt out per group; opting out releases today's pair."""
    date_text, timestamp = _beijing_date(now)
    async with database.transaction() as connection:
        if participating:
            cursor = await connection.execute(
                "DELETE FROM daily_spouse_optouts WHERE group_id = ? AND user_id = ?",
                (group_id, user_id),
            )
            return cursor.rowcount == 1, None
        cursor = await connection.execute(
            "INSERT OR IGNORE INTO daily_spouse_optouts"
            "(group_id, user_id, created_at) VALUES (?, ?, ?)",
            (group_id, user_id, timestamp),
        )
        released = await _release(connection, group_id, date_text, user_id, timestamp)
        return cursor.rowcount == 1, released
