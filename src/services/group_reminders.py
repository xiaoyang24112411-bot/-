"""Persistent, best-effort one-shot reminders; never replay uncertain deliveries."""

import asyncio
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from nonebot import logger
from nonebot.adapters.onebot.v11 import MessageSegment

from src.services.economy.database import EconomyDatabase

CHINA_TZ = timezone(timedelta(hours=8))
MAX_DELAY = 30 * 86400
MAX_LATENESS = 86400
CLAIM_TIMEOUT = 120
RETENTION = 30 * 86400
ACTIVE_STATUSES = ("pending", "claimed", "sending")
STATUS_LABELS = {
    "pending": "待提醒", "claimed": "准备发送", "sending": "发送中（结果待确认）",
    "sent": "已发送", "failed": "发送失败或结果未知（不会自动重发）",
    "cancelled": "已取消", "expired": "过期未发送",
}


class ReminderError(ValueError):
    """A reminder cannot be created or changed safely."""


@dataclass(frozen=True)
class GroupReminder:
    id: int
    bot_id: int
    group_id: int
    user_id: int
    request_id: str
    body: str
    due_at: int
    status: str
    created_at: int
    updated_at: int


def parse_reminder(argument: str, *, now: float | None = None) -> tuple[int, str]:
    """Only accept explicit intervals or unambiguous China-local date/time."""
    current = time.time() if now is None else now
    relative = re.fullmatch(
        r"([0-9]{1,8})\s*(秒钟?|分钟|分|小时|天)(?:后)?\s+(.+)",
        argument.strip(), re.DOTALL,
    )
    absolute = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})(?::(\d{2}))?\s+(.+)",
        argument.strip(), re.DOTALL,
    )
    if relative:
        quantity, unit, body = relative.groups()
        multiplier = {"秒": 1, "秒钟": 1, "分钟": 60, "分": 60, "小时": 3600, "天": 86400}
        delay = int(quantity) * multiplier[unit]
        due_at = int(current) + delay
    elif absolute:
        date, clock, seconds, body = absolute.groups()
        try:
            moment = datetime.strptime(
                f"{date} {clock}:{seconds or '00'}", "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=CHINA_TZ)
        except ValueError as exc:
            raise ReminderError("日期或时间无效，请使用：2026-09-23 08:00。") from exc
        due_at = int(moment.timestamp())
        delay = due_at - current
    else:
        raise ReminderError(
            "用法：提醒我 10分钟 喝水\n或：提醒我 2026-09-23 08:00 开会（北京时间）"
        )
    if delay < 5 or delay > MAX_DELAY:
        raise ReminderError("提醒时间须在 5 秒后到 30 天内，且不能是过去的时间。")
    body = body.strip()
    if not body or len(body) > 500:
        raise ReminderError("提醒内容须为 1～500 个字符。")
    return due_at, body


def format_due(due_at: int) -> str:
    return datetime.fromtimestamp(due_at, CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")


async def create_reminder(
    database: EconomyDatabase, *, bot_id: int, group_id: int, user_id: int,
    request_id: str, due_at: int, body: str, max_per_user: int = 10,
    max_per_group: int = 100, now: int | None = None,
) -> GroupReminder:
    current = int(time.time()) if now is None else now
    if not body.strip() or len(body) > 500:
        raise ReminderError("提醒内容须为 1～500 个字符。")
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT * FROM group_reminders WHERE bot_id=? AND group_id=? AND request_id=?",
            (bot_id, group_id, request_id),
        )
        existing = await cursor.fetchone()
        if existing:
            if existing["user_id"] != user_id:
                raise ReminderError("该消息编号已使用，请重新发送指令。")
            return GroupReminder(**dict(existing))
        if not 1 <= due_at - current <= MAX_DELAY:
            raise ReminderError("提醒时间已过期或超过 30 天，请重新设置。")
        cursor = await connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(user_id=?), 0) FROM group_reminders "
            "WHERE bot_id=? AND group_id=? AND status IN ('pending','claimed','sending')",
            (user_id, bot_id, group_id),
        )
        total, own = await cursor.fetchone()
        if own >= max_per_user or total >= max_per_group:
            raise ReminderError("待执行提醒数量已达上限，请先取消不需要的提醒。")
        cursor = await connection.execute(
            "INSERT INTO group_reminders "
            "(bot_id,group_id,user_id,request_id,body,due_at,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?) RETURNING *",
            (bot_id, group_id, user_id, request_id, body.strip(), due_at, current, current),
        )
        return GroupReminder(**dict(await cursor.fetchone()))


async def list_reminders(
    database: EconomyDatabase, bot_id: int, group_id: int, user_id: int,
) -> list[GroupReminder]:
    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT * FROM group_reminders WHERE bot_id=? AND group_id=? AND user_id=? "
            "ORDER BY status IN ('pending','claimed','sending') DESC, id DESC LIMIT 15",
            (bot_id, group_id, user_id),
        )
        return [GroupReminder(**dict(row)) for row in await cursor.fetchall()]


async def cancel_reminder(
    database: EconomyDatabase, *, reminder_id: int, bot_id: int, group_id: int,
    user_id: int, manager: bool = False, now: int | None = None,
) -> str:
    current = int(time.time()) if now is None else now
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT user_id,status FROM group_reminders WHERE id=? AND bot_id=? AND group_id=?",
            (reminder_id, bot_id, group_id),
        )
        row = await cursor.fetchone()
        if row is None or (row["user_id"] != user_id and not manager):
            raise ReminderError("没有找到该提醒，或你没有取消权限。")
        if row["status"] == "sending":
            raise ReminderError("该提醒已开始发送，无法保证取消；请稍后查看我的提醒。")
        if row["status"] not in {"pending", "claimed"}:
            return row["status"]
        await connection.execute(
            "UPDATE group_reminders SET status='cancelled',updated_at=? WHERE id=?",
            (current, reminder_id),
        )
        return "cancelled"


async def maintain_reminders(database: EconomyDatabase, *, now: int | None = None) -> None:
    current = int(time.time()) if now is None else now
    async with database.transaction() as connection:
        await connection.execute(
            "UPDATE group_reminders SET status='expired',updated_at=? "
            "WHERE status='pending' AND due_at < ?", (current, current - MAX_LATENESS),
        )
        await connection.execute(
            "UPDATE group_reminders SET status='failed',updated_at=? "
            "WHERE status IN ('claimed','sending') AND updated_at < ?",
            (current, current - CLAIM_TIMEOUT),
        )
        await connection.execute(
            "DELETE FROM group_reminders WHERE status NOT IN ('pending','claimed','sending') "
            "AND updated_at < ?", (current - RETENTION,),
        )


async def claim_due_reminders(
    database: EconomyDatabase, bot_ids: list[int], *, now: int | None = None, limit: int = 20,
) -> list[GroupReminder]:
    if not bot_ids:
        return []
    current = int(time.time()) if now is None else now
    placeholders = ",".join("?" for _ in bot_ids)
    async with database.transaction() as connection:
        cursor = await connection.execute(
            f"SELECT * FROM group_reminders WHERE bot_id IN ({placeholders}) "
            "AND status='pending' AND due_at BETWEEN ? AND ? ORDER BY due_at,id LIMIT ?",
            (*bot_ids, current - MAX_LATENESS, current, min(20, max(1, limit))),
        )
        rows = await cursor.fetchall()
        for row in rows:
            await connection.execute(
                "UPDATE group_reminders SET status='claimed',updated_at=? WHERE id=?",
                (current, row["id"]),
            )
        return [GroupReminder(**dict(row, status="claimed", updated_at=current)) for row in rows]


async def begin_reminder_send(
    database: EconomyDatabase, reminder_id: int, *, now: int | None = None,
) -> bool:
    current = int(time.time()) if now is None else now
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "UPDATE group_reminders SET status='sending',updated_at=? "
            "WHERE id=? AND status='claimed' AND due_at>=?",
            (current, reminder_id, current - MAX_LATENESS),
        )
        return cursor.rowcount == 1


async def finish_reminder_send(
    database: EconomyDatabase, reminder_id: int, *, sent: bool, now: int | None = None,
) -> None:
    current = int(time.time()) if now is None else now
    async with database.transaction() as connection:
        await connection.execute(
            "UPDATE group_reminders SET status=?,updated_at=? WHERE id=? AND status='sending'",
            ("sent" if sent else "failed", current, reminder_id),
        )


async def deliver_due_reminders(
    database: EconomyDatabase, bots: Mapping[str, Any], *, now: int | None = None,
    send_timeout: float = 15,
) -> int:
    """Probe actual QQ online state, atomically claim, then send at most 20 messages."""
    await maintain_reminders(database, now=now)
    online: dict[int, Any] = {}
    for bot in bots.values():
        try:
            status = await asyncio.wait_for(bot.get_status(), timeout=5)
            if status.get("online") is True and status.get("good") is True:
                online[int(bot.self_id)] = bot
        except Exception as exc:
            logger.warning("Reminder online probe failed: {}", type(exc).__name__)
    reminders = await claim_due_reminders(database, list(online), now=now)
    semaphore = asyncio.Semaphore(4)

    async def deliver(item: GroupReminder) -> int:
        async with semaphore:
            if not await begin_reminder_send(database, item.id, now=now):
                return 0
            sent = False
            try:
                await asyncio.wait_for(
                    online[item.bot_id].send_group_msg(
                        group_id=item.group_id,
                        message=MessageSegment.at(item.user_id) + MessageSegment.text(
                            f" 提醒 #{item.id}：{item.body}"
                        ),
                    ),
                    timeout=send_timeout,
                )
                sent = True
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Reminder delivery failed: reminder={} bot={} group={} error={}",
                    item.id, item.bot_id, item.group_id, type(exc).__name__,
                )
            finally:
                await asyncio.shield(finish_reminder_send(database, item.id, sent=sent, now=now))
            if sent:
                logger.info("Reminder sent: reminder={} group={}", item.id, item.group_id)
            return int(sent)

    results = await asyncio.gather(*(deliver(item) for item in reminders))
    return sum(results)
