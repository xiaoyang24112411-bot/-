"""Owner-only global QQ block management and early message interception."""

import re

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.exception import FinishedException, IgnoredException
from nonebot.message import event_preprocessor
from nonebot.rule import Rule

from src.config import AUTO_CHAT_CONTROLLER_ID
from src.services.economy import get_economy_database
from src.services.global_blacklist import block_user, is_blocked, list_blocked, unblock_user

_COMMAND = re.compile(r"^/?(?P<name>解除拉黑|查看黑名单|黑名单|放出|拉黑)(?=\s|$)")
_QQ_ID = re.compile(r"[0-9]{5,19}")


def _is_management_command(event: MessageEvent) -> bool:
    return _COMMAND.match(event.get_plaintext().strip()) is not None


management = on_message(rule=Rule(_is_management_command), priority=3, block=True)


def _parse_target(event: MessageEvent) -> int | None:
    text = event.get_plaintext().strip()
    command = _COMMAND.match(text)
    argument = text[command.end():].strip() if command else ""
    mentions = [str(segment.data.get("qq", "")) for segment in event.get_message()
                if segment.type == "at"]
    candidates = ([argument] if argument else []) + mentions
    if len(candidates) != 1 or not _QQ_ID.fullmatch(candidates[0]):
        return None
    user_id = int(candidates[0])
    return user_id if 0 < user_id <= 2**63 - 1 else None


@event_preprocessor
async def reject_blocked_messages(event: MessageEvent) -> None:
    if event.user_id in (event.self_id, AUTO_CHAT_CONTROLLER_ID):
        return
    try:
        blocked = await is_blocked(get_economy_database(), event.user_id)
    except Exception as exc:
        logger.exception("Global blacklist lookup failed; message blocked as a precaution")
        raise IgnoredException("global blacklist unavailable") from exc
    if blocked:
        raise IgnoredException("sender is in the global blacklist")


@management.handle()
async def handle_management(bot: Bot, event: MessageEvent) -> None:
    if event.user_id != AUTO_CHAT_CONTROLLER_ID:
        return
    text = event.get_plaintext().strip()
    match = _COMMAND.match(text)
    if match is None:
        return
    name = match.group("name")
    database = get_economy_database()
    try:
        if name in {"黑名单", "查看黑名单"}:
            argument = text[match.end():].strip()
            if not argument:
                page = 1
            elif re.fullmatch(r"[0-9]{1,4}", argument) and int(argument) > 0:
                page = int(argument)
            else:
                await management.finish("用法：黑名单 [页码]")
                return
            total, members = await list_blocked(database, page)
            if total == 0:
                await management.finish("全局黑名单为空。")
            total_pages = (total + 19) // 20
            if page > total_pages:
                await management.finish(f"只有 {total_pages} 页黑名单。")
            await management.finish(
                f"全局黑名单（{page}/{total_pages} 页，共 {total} 人）：\n"
                + "\n".join(str(user_id) for user_id in members)
            )
            return

        target = _parse_target(event)
        if target is None:
            await management.finish(f"用法：{name} QQ号，或在群里发送 {name} @群友（一次一人）")
            return
        if target in (AUTO_CHAT_CONTROLLER_ID, int(bot.self_id)):
            await management.finish("不能拉黑或放出终极管理员和机器人自身。")
            return
        if name == "拉黑":
            changed = await block_user(database, target, event.user_id)
            status = "已加入" if changed else "已在"
            await management.finish(
                f"QQ {target} {status}全局黑名单；所有群聊和私聊均不再回复其消息。"
            )
        else:
            changed = await unblock_user(database, target)
            status = "已移出" if changed else "不在"
            await management.finish(f"QQ {target} {status}全局黑名单。")
    except FinishedException:
        raise
    except Exception:
        logger.exception("Global blacklist management failed")
        await management.finish("黑名单操作失败，请检查数据库和机器人日志。")
