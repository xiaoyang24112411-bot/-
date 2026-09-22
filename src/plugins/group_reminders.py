"""Explicit, group-only reminder commands and a restart-safe polling worker."""

import asyncio
import re
from contextlib import suppress

import nonebot
from nonebot import get_driver, logger, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_community_settings
from src.services.economy import get_economy_database
from src.services.economy.commands import command_text
from src.services.group_reminders import (
    STATUS_LABELS,
    ReminderError,
    cancel_reminder,
    create_reminder,
    deliver_due_reminders,
    format_due,
    list_reminders,
    parse_reminder,
)
from src.services.permissions import is_group_manager

COMMANDS = ("提醒我", "我的提醒", "取消提醒")
polling_task: asyncio.Task | None = None


def is_reminder(event: MessageEvent) -> bool:
    return (
        isinstance(event, GroupMessageEvent)
        and event.user_id != event.self_id
        and str(event.user_id) not in nonebot.get_bots()
        and getattr(event.sender, "is_bot", False) is not True
        and getattr(event, "is_bot", False) is not True
        and getattr(event.sender, "is_bot", False) is not True
        and any(command_text(event, command) is not None for command in COMMANDS)
    )


reminder = on_message(rule=Rule(is_reminder), priority=10, block=True)


@reminder.handle()
async def handle_reminder(event: GroupMessageEvent) -> None:
    settings = get_community_settings()
    response = ""
    try:
        if not settings.reminders_enabled:
            raise ReminderError("定时提醒功能暂未启用。")
        if any(segment.type != "text" for segment in event.original_message):
            raise ReminderError("提醒只接受纯文字，只会 @ 发起者本人，请勿附带 @ 或图片。")
        database = get_economy_database()
        argument = command_text(event, "提醒我")
        if argument is not None:
            due_at, body = parse_reminder(argument)
            item = await create_reminder(
                database, bot_id=event.self_id, group_id=event.group_id,
                user_id=event.user_id, request_id=str(event.message_id),
                due_at=due_at, body=body,
                max_per_user=settings.reminders_max_active_per_user,
                max_per_group=settings.reminders_max_active_per_group,
            )
            response = (
                f"提醒 #{item.id}：{STATUS_LABELS[item.status]}\n"
                f"北京时间 {format_due(item.due_at)}\n{item.body}\n"
                f"取消：取消提醒 {item.id}\n离线后恢复最多补发 24 小时内的提醒。"
            )
        elif command_text(event, "我的提醒") is not None:
            items = await list_reminders(
                database, event.self_id, event.group_id, event.user_id,
            )
            response = "本群我的提醒（最多显示 15 条，终态保留 30 天）：\n" + "\n".join(
                f"#{item.id} [{STATUS_LABELS[item.status]}] {format_due(item.due_at)}\n"
                f"{item.body[:100]}" for item in items
            ) if items else "你在本群还没有提醒。"
        else:
            argument = command_text(event, "取消提醒") or ""
            if not re.fullmatch(r"#?[0-9]{1,18}", argument):
                raise ReminderError("用法：取消提醒 编号，例如：取消提醒 12")
            status = await cancel_reminder(
                database, reminder_id=int(argument.lstrip("#")), bot_id=event.self_id,
                group_id=event.group_id, user_id=event.user_id, manager=is_group_manager(event),
            )
            response = f"提醒 #{argument.lstrip('#')}：{STATUS_LABELS[status]}。"
    except ReminderError as exc:
        response = str(exc)
    except Exception as exc:
        logger.warning("Reminder command failed: group={} error={}",
                       event.group_id, type(exc).__name__)
        response = "提醒操作失败，请稍后重试；用“我的提醒”查看是否已经保存。"
    try:
        await reminder.send(MessageSegment.text(response))
    except Exception as exc:
        logger.warning("Reminder response failed: group={} error={}",
                       event.group_id, type(exc).__name__)


async def _poll_once() -> int:
    if not get_community_settings().reminders_enabled:
        return 0
    bots = {key: bot for key, bot in nonebot.get_bots().items() if isinstance(bot, Bot)}
    return await deliver_due_reminders(get_economy_database(), bots)


async def _poll_loop() -> None:
    while True:
        try:
            await _poll_once()
        except Exception as exc:
            logger.warning("Reminder poll failed: {}", type(exc).__name__)
        await asyncio.sleep(max(1, get_community_settings().reminder_poll_seconds))


@get_driver().on_startup
async def start_reminder_polling() -> None:
    global polling_task
    if polling_task is None or polling_task.done():
        polling_task = asyncio.create_task(_poll_loop())


@get_driver().on_shutdown
async def stop_reminder_polling() -> None:
    global polling_task
    if polling_task is not None:
        polling_task.cancel()
        with suppress(asyncio.CancelledError):
            await polling_task
        polling_task = None
