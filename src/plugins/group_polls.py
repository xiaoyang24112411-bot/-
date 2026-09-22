"""Explicit group poll commands; no AI API or external service required."""

import re

from nonebot import get_bots, logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_community_settings
from src.services.economy.database import get_economy_database
from src.services.group_polls import (
    MAX_INPUT_LENGTH,
    PollError,
    cast_vote,
    close_poll,
    create_poll,
    format_poll,
    get_poll,
    list_polls,
    parse_poll_creation,
    parse_poll_id,
)
from src.services.permissions import is_group_manager

COMMAND = re.compile(r"^/?(发起投票|投票结果|投票列表|结束投票|投票)(?:\s+([\s\S]*))?$")
USAGE = (
    "群投票用法：\n发起投票 吃什么 | 火锅 | 烧烤\n投票 编号 选项编号\n"
    "投票结果 编号\n投票列表\n结束投票 编号\n每人一票，可改票；不会消耗积分。"
)


def is_poll_command(event: MessageEvent) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return False
    if not get_community_settings().polls_enabled:
        return False
    if event.user_id == event.self_id or str(event.user_id) in get_bots():
        return False
    if getattr(event.sender, "is_bot", False):
        return False
    # Only explicit textual commands. Embedded images/CQ control segments aren't input.
    if any(segment.type != "text" for segment in event.original_message):
        return False
    return COMMAND.fullmatch(event.get_plaintext().strip()) is not None


group_poll = on_message(rule=Rule(is_poll_command), priority=10, block=True)


async def _run_command(event: GroupMessageEvent) -> str:
    match = COMMAND.fullmatch(event.get_plaintext().strip())
    if match is None:
        return USAGE
    command, argument = match.group(1), (match.group(2) or "").strip()
    if len(argument) > MAX_INPUT_LENGTH:
        raise PollError("投票指令过长，最多 800 字。")
    database = get_economy_database()
    scope = {"bot_id": event.self_id, "group_id": event.group_id}
    if command == "发起投票":
        if not argument:
            return USAGE
        title, options = parse_poll_creation(argument)
        poll = await create_poll(
            database, **scope, user_id=event.user_id, title=title, options=options,
            request_id=str(event.message_id),
            max_active=get_community_settings().polls_max_active_per_group,
        )
        return format_poll(poll)
    if command == "投票列表":
        if argument:
            return USAGE
        polls = await list_polls(database, **scope)
        if not polls:
            return "本群暂无进行中的投票。\n" + USAGE
        return "本群进行中的投票：\n" + "\n".join(
            f"#{poll.id} {poll.title}（{sum(poll.counts)} 人投票）" for poll in polls
        )
    arguments = argument.split()
    if len(arguments) != (2 if command == "投票" else 1):
        return USAGE
    poll_id = parse_poll_id(arguments[0])
    if command == "投票":
        option_number = parse_poll_id(arguments[1])
        poll = await cast_vote(
            database, **scope, poll_id=poll_id, user_id=event.user_id,
            option_number=option_number,
        )
        return f"已选择第 {option_number} 项（重复投票会更新选择）。\n" + format_poll(poll)
    if command == "结束投票":
        poll = await close_poll(
            database, **scope, poll_id=poll_id, user_id=event.user_id,
            is_manager=is_group_manager(event),
        )
    else:
        poll = await get_poll(database, **scope, poll_id=poll_id)
    return format_poll(poll)


@group_poll.handle()
async def handle_poll_command(event: GroupMessageEvent) -> None:
    try:
        result = await _run_command(event)
    except PollError as exc:
        result = str(exc)
    except Exception:
        logger.exception("Group poll operation failed, group={}", event.group_id)
        result = "投票操作失败，请稍后重试；积分不会受到影响。"
    try:
        # User-supplied titles/options are always text, never parsed as CQ codes.
        await group_poll.send(MessageSegment.text(result))
    except Exception:
        logger.exception("Group poll response failed, group={}", event.group_id)
