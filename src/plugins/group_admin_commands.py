"""OneBot V11 group moderation commands."""

from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent
from nonebot.params import CommandArg

from src.services.economy.commands import mentioned_user
from src.services.permissions import is_group_manager

ban = on_command("ban", priority=6, block=True)
unban = on_command("unban", priority=6, block=True)
kick = on_command("kick", priority=6, block=True)
set_title = on_command("set_title", aliases={"设置头衔"}, priority=6, block=True)
ban_all = on_command("ban_all", priority=6, block=True)
unban_all = on_command("unban_all", priority=6, block=True)
withdraw = on_command("withdraw", priority=6, block=True)


async def _group_and_permission(matcher, event: MessageEvent) -> GroupMessageEvent:
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("此指令只能在群聊中使用。")
    if not is_group_manager(event):
        await matcher.finish("只有群主、群管理员或机器人终极管理员可以执行此操作。")
    return event


def _target(event: GroupMessageEvent) -> int | None:
    target = mentioned_user(event)
    return target if target not in {event.self_id, event.user_id} else None


async def _api_error(matcher, action: str) -> None:
    logger.exception(f"Group management action failed: {action}")
    await matcher.finish(f"{action}失败，请确认机器人具有群管理员权限。")


@ban.handle()
async def handle_ban(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:  # noqa: B008
    group = await _group_and_permission(ban, event)
    target = _target(group)
    values = args.extract_plain_text().split()
    if target is None or not values or not values[-1].isdigit():
        await ban.finish("用法：/ban @群友 分钟，例如：/ban @群友 10")
    minutes = int(values[-1])
    if not 1 <= minutes <= 43_200:
        await ban.finish("禁言时长必须为 1～43200 分钟。")
    try:
        await bot.set_group_ban(group_id=group.group_id, user_id=target, duration=minutes * 60)
    except Exception:
        await _api_error(ban, "禁言")
    await ban.finish(f"已禁言 QQ {target}，时长 {minutes} 分钟。")


@unban.handle()
async def handle_unban(bot: Bot, event: MessageEvent) -> None:
    group = await _group_and_permission(unban, event)
    target = _target(group)
    if target is None:
        await unban.finish("用法：/unban @群友")
    try:
        await bot.set_group_ban(group_id=group.group_id, user_id=target, duration=0)
    except Exception:
        await _api_error(unban, "解除禁言")
    await unban.finish(f"已解除 QQ {target} 的禁言。")


@kick.handle()
async def handle_kick(bot: Bot, event: MessageEvent) -> None:
    group = await _group_and_permission(kick, event)
    target = _target(group)
    if target is None:
        await kick.finish("用法：/kick @群友 [理由]")
    try:
        await bot.set_group_kick(group_id=group.group_id, user_id=target, reject_add_request=False)
    except Exception:
        await _api_error(kick, "移出群聊")
    await kick.finish(f"已将 QQ {target} 移出群聊。")


@set_title.handle()
async def handle_set_title(
    bot: Bot, event: MessageEvent, args: Message = CommandArg()  # noqa: B008
) -> None:
    group = await _group_and_permission(set_title, event)
    target = _target(group)
    title = args.extract_plain_text().strip()
    if target is None or not title:
        await set_title.finish("用法：/set_title @群友 头衔")
    if len(title) > 18:
        await set_title.finish("群头衔请控制在 18 个字符以内。")
    try:
        await bot.set_group_special_title(
            group_id=group.group_id, user_id=target, special_title=title, duration=-1
        )
    except Exception:
        await _api_error(set_title, "设置群头衔")
    await set_title.finish(f"已为 QQ {target} 设置群头衔：{title}")


@ban_all.handle()
async def handle_ban_all(bot: Bot, event: MessageEvent) -> None:
    group = await _group_and_permission(ban_all, event)
    try:
        await bot.set_group_whole_ban(group_id=group.group_id, enable=True)
    except Exception:
        await _api_error(ban_all, "开启全员禁言")
    await ban_all.finish("已开启全员禁言。")


@unban_all.handle()
async def handle_unban_all(bot: Bot, event: MessageEvent) -> None:
    group = await _group_and_permission(unban_all, event)
    try:
        await bot.set_group_whole_ban(group_id=group.group_id, enable=False)
    except Exception:
        await _api_error(unban_all, "关闭全员禁言")
    await unban_all.finish("已关闭全员禁言。")


def _reply_message_id(event: GroupMessageEvent) -> int | None:
    for segment in event.get_message():
        if segment.type == "reply":
            try:
                return int(segment.data["id"])
            except (KeyError, TypeError, ValueError):
                return None
    return None


@withdraw.handle()
async def handle_withdraw(bot: Bot, event: MessageEvent) -> None:
    group = await _group_and_permission(withdraw, event)
    message_id = _reply_message_id(group)
    if message_id is None:
        try:
            payload = await bot.call_api(
                "get_group_msg_history", group_id=group.group_id, count=50
            )
            messages = payload.get("messages", []) if isinstance(payload, dict) else []
            own_messages = [
                item
                for item in messages
                if str(item.get("user_id") or item.get("sender", {}).get("user_id"))
                == str(bot.self_id)
            ]
            if own_messages:
                latest = max(own_messages, key=lambda item: int(item.get("time", 0)))
                message_id = int(latest["message_id"])
        except Exception:
            logger.exception("Failed to get group message history")
    if message_id is None:
        await withdraw.finish("没有找到可撤回的机器人消息；也可回复目标消息后发送 /withdraw。")
    try:
        await bot.delete_msg(message_id=message_id)
    except Exception:
        await _api_error(withdraw, "撤回消息")
    await withdraw.finish("已撤回目标消息。")
