"""Opt-in group message recording and word-cloud commands."""

import asyncio

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_ai_feature_settings, get_app_settings
from src.services.ai_features import AIFeatureError
from src.services.ai_features.wordclouds import (
    clear_wordcloud_messages,
    generate_wordcloud,
    get_wordcloud_messages,
    get_wordcloud_setting,
    record_wordcloud_message,
    resolve_wordcloud_font,
    set_wordcloud_enabled,
)
from src.services.economy import get_economy_database
from src.services.economy.commands import command_text


def _rule(command: str) -> Rule:
    return Rule(lambda event: command_text(event, command) is not None)


enable_wordcloud = on_message(rule=_rule("开启词云记录"), priority=10, block=True)
disable_wordcloud = on_message(rule=_rule("关闭词云记录"), priority=10, block=True)
wordcloud_status = on_message(rule=_rule("词云状态"), priority=10, block=True)
create_wordcloud = on_message(rule=_rule("生成词云"), priority=10, block=True)
clear_wordcloud = on_message(rule=_rule("清空词云记录"), priority=10, block=True)
message_recorder = on_message(priority=99, block=False)


def _require_manager(event: GroupMessageEvent) -> None:
    is_group_manager = event.sender.role in {"owner", "admin"}
    is_global_admin = event.user_id in get_app_settings().admin_ids
    if not is_group_manager and not is_global_admin:
        raise AIFeatureError("只有群主、群管理员或机器人管理员可以管理词云记录。")


@enable_wordcloud.handle()
async def handle_enable_wordcloud(event: GroupMessageEvent) -> None:
    try:
        _require_manager(event)
        argument = (command_text(event, "开启词云记录") or "").strip()
        default_days = get_ai_feature_settings().wordcloud_retention_days
        if argument and not argument.isdigit():
            raise AIFeatureError("用法：开启词云记录 [保留天数]，天数范围 1～90。")
        days = int(argument) if argument else default_days
        if not 1 <= days <= 90:
            raise AIFeatureError("词云记录保留天数必须在 1～90 之间。")
        setting = await set_wordcloud_enabled(
            get_economy_database(), event.group_id, True, event.user_id, days
        )
    except AIFeatureError as exc:
        await enable_wordcloud.finish(str(exc))
    await enable_wordcloud.finish(
        f"本群词云记录已开启，将保存纯文本消息 {setting.retention_days} 天。\n"
        "可随时发送“关闭词云记录”停止收集，或“清空词云记录”删除数据。"
    )


@disable_wordcloud.handle()
async def handle_disable_wordcloud(event: GroupMessageEvent) -> None:
    try:
        _require_manager(event)
        current = await get_wordcloud_setting(
            get_economy_database(),
            event.group_id,
            get_ai_feature_settings().wordcloud_retention_days,
        )
        await set_wordcloud_enabled(
            get_economy_database(),
            event.group_id,
            False,
            event.user_id,
            current.retention_days,
        )
    except AIFeatureError as exc:
        await disable_wordcloud.finish(str(exc))
    await disable_wordcloud.finish("本群词云记录已关闭；已有记录仍可生成或手动清空。")


@wordcloud_status.handle()
async def handle_wordcloud_status(event: GroupMessageEvent) -> None:
    setting = await get_wordcloud_setting(
        get_economy_database(),
        event.group_id,
        get_ai_feature_settings().wordcloud_retention_days,
    )
    state = "已开启" if setting.enabled else "未开启"
    await wordcloud_status.finish(f"本群词云记录：{state}｜保留 {setting.retention_days} 天")


@create_wordcloud.handle()
async def handle_create_wordcloud(event: GroupMessageEvent) -> None:
    argument = (command_text(event, "生成词云") or "").strip()
    if argument and not argument.isdigit():
        await create_wordcloud.finish("用法：生成词云 [统计天数]，天数范围 1～90。")
    days = int(argument) if argument else 7
    if not 1 <= days <= 90:
        await create_wordcloud.finish("词云统计天数必须在 1～90 之间。")
    try:
        messages = await get_wordcloud_messages(get_economy_database(), event.group_id, days)
        font = resolve_wordcloud_font(get_ai_feature_settings().wordcloud_font_path)
        image = await asyncio.to_thread(generate_wordcloud, messages, font)
    except AIFeatureError as exc:
        await create_wordcloud.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Word cloud generation failed")
        await create_wordcloud.finish("词云生成失败，请稍后再试。")
    await create_wordcloud.finish(MessageSegment.image(image) + f"\n本群最近 {days} 天词云")


@clear_wordcloud.handle()
async def handle_clear_wordcloud(event: GroupMessageEvent) -> None:
    try:
        _require_manager(event)
        count = await clear_wordcloud_messages(get_economy_database(), event.group_id)
    except AIFeatureError as exc:
        await clear_wordcloud.finish(str(exc))
    await clear_wordcloud.finish(f"已清空本群 {count} 条词云消息记录。")


@message_recorder.handle()
async def handle_message_recorder(event: GroupMessageEvent) -> None:
    try:
        await record_wordcloud_message(
            get_economy_database(),
            event.group_id,
            event.user_id,
            event.get_plaintext(),
        )
    except Exception:
        logger.exception("Word cloud message recording failed")
