"""Group RSS subscriptions with safe background polling."""

import asyncio

import nonebot
from nonebot import get_driver, logger, on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageEvent
from nonebot.params import CommandArg

from src.config import get_subscription_settings
from src.services.economy import get_economy_database
from src.services.permissions import is_group_manager
from src.services.subscriptions import (
    SubscriptionError,
    add_rss_subscription,
    delete_rss_subscription,
    fetch_feed,
    list_rss_subscriptions,
    mark_rss_entry,
)

rss = on_command("rss", priority=10, block=True)
polling_task: asyncio.Task | None = None


@rss.handle()
async def handle_rss(event: MessageEvent, args: Message = CommandArg()) -> None:  # noqa: B008
    if not isinstance(event, GroupMessageEvent):
        await rss.finish("RSS 订阅只能在群聊中管理。")
    if not is_group_manager(event):
        await rss.finish("只有群主、群管理员或机器人终极管理员可以管理 RSS 订阅。")
    text = args.extract_plain_text().strip()
    action, _, argument = text.partition(" ")
    action = action.lower()
    try:
        if action == "add":
            if not argument.strip():
                raise SubscriptionError("用法：/rss add RSS链接")
            feed = await fetch_feed(argument.strip())
            item = await add_rss_subscription(
                get_economy_database(),
                group_id=event.group_id,
                url=argument.strip(),
                created_by=event.user_id,
                feed=feed,
            )
            await rss.finish(f"RSS 订阅成功：#{item.id} {item.title}\n后续只推送新内容。")
        if action in {"del", "delete", "remove"}:
            removed = await delete_rss_subscription(
                get_economy_database(), event.group_id, argument
            )
            await rss.finish("RSS 订阅已删除。" if removed else "没有找到对应的 RSS 订阅。")
        if action == "list":
            items = await list_rss_subscriptions(get_economy_database(), event.group_id)
            if not items:
                await rss.finish("本群尚未添加 RSS 订阅。")
            lines = ["本群 RSS 订阅："]
            lines.extend(f"#{item.id} {item.title}\n{item.feed_url}" for item in items)
            await rss.finish("\n".join(lines))
        raise SubscriptionError("用法：/rss add 链接｜/rss del 编号或链接｜/rss list")
    except SubscriptionError as exc:
        await rss.finish(str(exc))


async def _poll_once() -> None:
    bots = nonebot.get_bots()
    if not bots:
        return
    bot = next(iter(bots.values()))
    items = await list_rss_subscriptions(get_economy_database())
    for item in items:
        try:
            feed = await fetch_feed(item.feed_url)
            latest = feed.entries[0]
            if latest.entry_id == item.last_entry_id:
                continue
            await bot.send_group_msg(
                group_id=item.group_id,
                message=f"【RSS更新｜{feed.title}】\n{latest.title}\n{latest.link}",
            )
            await mark_rss_entry(get_economy_database(), item.id, latest.entry_id, feed.title)
        except Exception:
            logger.exception(f"RSS poll failed: subscription={item.id}")


async def _poll_loop() -> None:
    interval = get_subscription_settings().rss_poll_seconds
    while True:
        await asyncio.sleep(interval)
        await _poll_once()


@get_driver().on_startup
async def start_rss_polling() -> None:
    global polling_task
    polling_task = asyncio.create_task(_poll_loop())


@get_driver().on_shutdown
async def stop_rss_polling() -> None:
    if polling_task is not None:
        polling_task.cancel()
