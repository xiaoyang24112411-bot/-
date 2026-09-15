"""Bilibili dynamic and live notifications for groups."""

import asyncio

import nonebot
from nonebot import get_driver, logger, on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageEvent
from nonebot.params import CommandArg

from src.config import get_subscription_settings
from src.services.bilibili import (
    BilibiliError,
    add_bilibili_subscription,
    delete_bilibili_subscription,
    fetch_bilibili_state,
    list_bilibili_subscriptions,
    mark_bilibili_state,
)
from src.services.economy import get_economy_database
from src.services.permissions import is_group_manager

bili_sub = on_command("bili_sub", priority=10, block=True)
bili_unsub = on_command("bili_unsub", priority=10, block=True)
bili_list = on_command("bili_list", priority=10, block=True)
polling_task: asyncio.Task | None = None


async def _require_group_manager(matcher, event: MessageEvent) -> GroupMessageEvent:
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("B站订阅只能在群聊中管理。")
    if not is_group_manager(event):
        await matcher.finish("只有群主、群管理员或机器人终极管理员可以管理B站订阅。")
    return event


def _uid(args: Message) -> int | None:
    text = args.extract_plain_text().strip()
    return int(text) if text.isdigit() and int(text) > 0 else None


@bili_sub.handle()
async def handle_bili_sub(event: MessageEvent, args: Message = CommandArg()) -> None:  # noqa: B008
    group = await _require_group_manager(bili_sub, event)
    uid = _uid(args)
    if uid is None:
        await bili_sub.finish("用法：/bili_sub 主播UID")
    try:
        state = await fetch_bilibili_state(uid, get_subscription_settings())
        await add_bilibili_subscription(
            get_economy_database(), group_id=group.group_id, created_by=group.user_id, state=state
        )
    except BilibiliError as exc:
        await bili_sub.finish(str(exc))
    await bili_sub.finish(f"已订阅 {state.display_name}（UID {uid}）的动态和开播提醒。")


@bili_unsub.handle()
async def handle_bili_unsub(event: MessageEvent, args: Message = CommandArg()) -> None:  # noqa: B008
    group = await _require_group_manager(bili_unsub, event)
    uid = _uid(args)
    if uid is None:
        await bili_unsub.finish("用法：/bili_unsub 主播UID")
    removed = await delete_bilibili_subscription(
        get_economy_database(), group.group_id, uid
    )
    await bili_unsub.finish("B站订阅已取消。" if removed else "本群没有订阅该 UID。")


@bili_list.handle()
async def handle_bili_list(event: MessageEvent) -> None:
    group = await _require_group_manager(bili_list, event)
    items = await list_bilibili_subscriptions(get_economy_database(), group.group_id)
    if not items:
        await bili_list.finish("本群尚未添加B站订阅。")
    await bili_list.finish(
        "本群B站订阅：\n"
        + "\n".join(f"{item.display_name}（UID {item.uid}）" for item in items)
    )


async def _poll_once() -> None:
    bots = nonebot.get_bots()
    if not bots:
        return
    bot = next(iter(bots.values()))
    settings = get_subscription_settings()
    for item in await list_bilibili_subscriptions(get_economy_database()):
        try:
            state = await fetch_bilibili_state(item.uid, settings)
            messages: list[str] = []
            if state.dynamic_id and state.dynamic_id != item.last_dynamic_id:
                messages.append(
                    f"【B站动态｜{state.display_name}】\n{state.dynamic_text}\n{state.dynamic_url}"
                )
            if state.live_status == 1 and item.last_live_status != 1:
                messages.append(
                    f"【B站开播｜{state.display_name}】\n{state.live_title}\n{state.live_url}"
                )
            for message in messages:
                await bot.send_group_msg(group_id=item.group_id, message=message)
            await mark_bilibili_state(get_economy_database(), item.group_id, state)
        except Exception:
            logger.exception(f"Bilibili poll failed: group={item.group_id}, uid={item.uid}")


async def _poll_loop() -> None:
    interval = get_subscription_settings().bili_poll_seconds
    while True:
        await asyncio.sleep(interval)
        await _poll_once()


@get_driver().on_startup
async def start_bili_polling() -> None:
    global polling_task
    polling_task = asyncio.create_task(_poll_loop())


@get_driver().on_shutdown
async def stop_bili_polling() -> None:
    if polling_task is not None:
        polling_task.cancel()
