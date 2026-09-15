"""Opt-in group recall cache with manager-only viewing."""

from nonebot import on_message, on_notice
from nonebot.adapters.onebot.v11 import GroupMessageEvent, GroupRecallNoticeEvent
from nonebot.rule import Rule

from src.services.economy import get_economy_database
from src.services.economy.commands import command_text
from src.services.permissions import is_group_manager
from src.services.recall_cache import (
    CachedMessage,
    is_recall_enabled,
    latest_recalled,
    remember_message,
    remember_recall,
    set_recall_enabled,
)


def _rule(command: str) -> Rule:
    return Rule(lambda event: command_text(event, command) is not None)


enable_recall = on_message(rule=_rule("开启撤回记录"), priority=5, block=True)
disable_recall = on_message(rule=_rule("关闭撤回记录"), priority=5, block=True)
view_recall = on_message(rule=_rule("查看撤回"), priority=5, block=True)
recall_notice = on_notice(priority=20, block=False)
recall_recorder = on_message(priority=98, block=False)


async def _require_manager(matcher, event: GroupMessageEvent) -> None:
    if not is_group_manager(event):
        await matcher.finish("只有群主、群管理员或机器人终极管理员可以管理撤回记录。")


@enable_recall.handle()
async def handle_enable_recall(event: GroupMessageEvent) -> None:
    await _require_manager(enable_recall, event)
    await set_recall_enabled(get_economy_database(), event.group_id, True, event.user_id)
    await enable_recall.finish(
        "本群撤回记录已开启。仅缓存开启后机器人看到的纯文本，重启即清空；仅管理者可查看。"
    )


@disable_recall.handle()
async def handle_disable_recall(event: GroupMessageEvent) -> None:
    await _require_manager(disable_recall, event)
    await set_recall_enabled(get_economy_database(), event.group_id, False, event.user_id)
    await disable_recall.finish("本群撤回记录已关闭，内存缓存已清空。")


@view_recall.handle()
async def handle_view_recall(event: GroupMessageEvent) -> None:
    await _require_manager(view_recall, event)
    if not await is_recall_enabled(get_economy_database(), event.group_id):
        await view_recall.finish("本群尚未开启撤回记录。")
    record = latest_recalled(event.group_id)
    if record is None:
        await view_recall.finish("暂时没有捕获到可查看的撤回文本。")
    await view_recall.finish(
        f"最近撤回｜发送者 QQ {record.user_id}｜操作者 QQ {record.operator_id}\n"
        f"内容：{record.text}"
    )


@recall_notice.handle()
async def handle_recall_notice(event: GroupRecallNoticeEvent) -> None:
    if await is_recall_enabled(get_economy_database(), event.group_id):
        remember_recall(event.group_id, event.message_id, event.operator_id)


@recall_recorder.handle()
async def handle_recall_recorder(event: GroupMessageEvent) -> None:
    if not await is_recall_enabled(get_economy_database(), event.group_id):
        return
    remember_message(
        event.group_id,
        CachedMessage(
            message_id=event.message_id,
            user_id=event.user_id,
            text=event.get_plaintext()[:1000],
            sent_at=event.time,
        ),
    )
