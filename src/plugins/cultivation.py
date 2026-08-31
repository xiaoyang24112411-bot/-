"""Persistent '牛牛修仙' text game commands."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_economy_settings
from src.services.economy import EconomyError, get_economy_database
from src.services.economy.commands import command_text, message_request_id
from src.services.games.cultivation import (
    breakthrough,
    cultivate,
    get_cultivation_profile,
)


def _rule(*commands: str) -> Rule:
    def matches(event: GroupMessageEvent) -> bool:
        return any(command_text(event, command) is not None for command in commands)

    return Rule(matches)


cultivation_status = on_message(
    rule=_rule("牛牛修仙", "修仙状态"),
    priority=10,
    block=True,
)
cultivate_matcher = on_message(rule=_rule("修炼"), priority=10, block=True)
breakthrough_matcher = on_message(rule=_rule("突破"), priority=10, block=True)


def _profile_text(profile) -> str:
    if profile.next_realm_name is None:
        progress = "已达最高境界"
    else:
        progress = f"下一境界：{profile.next_realm_name} （需要 {profile.next_requirement} 修为）"
    return (
        f"境界：{profile.realm_name}\n修为：{profile.cultivation}\n"
        f"灵石：{profile.spirit_stones}\n{progress}"
    )


@cultivation_status.handle()
async def handle_cultivation_status(event: GroupMessageEvent) -> None:
    try:
        profile = await get_cultivation_profile(
            get_economy_database(), event.group_id, event.user_id
        )
    except Exception:
        logger.exception("Cultivation profile lookup failed")
        await cultivation_status.finish("修仙状态查询失败，请稍后再试。")
    await cultivation_status.finish(
        MessageSegment.at(event.user_id)
        + " 牛牛修仙\n"
        + _profile_text(profile)
        + "\n指令：修炼｜突破｜修仙状态"
    )


@cultivate_matcher.handle()
async def handle_cultivate(event: GroupMessageEvent) -> None:
    try:
        result = await cultivate(
            get_economy_database(),
            group_id=event.group_id,
            user_id=event.user_id,
            request_id=message_request_id(event, "cultivate"),
            cooldown_seconds=get_economy_settings().cultivation_cooldown_seconds,
        )
    except EconomyError as exc:
        await cultivate_matcher.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Cultivation action failed")
        await cultivate_matcher.finish("修炼失败，请稍后再试。")
    await cultivate_matcher.finish(
        MessageSegment.at(event.user_id)
        + f" 吐纳灵气，修为 +{result.cultivation_gain}，灵石 +{result.spirit_stone_gain}\n"
        + _profile_text(result.profile)
    )


@breakthrough_matcher.handle()
async def handle_breakthrough(event: GroupMessageEvent) -> None:
    try:
        profile = await breakthrough(
            get_economy_database(),
            group_id=event.group_id,
            user_id=event.user_id,
            request_id=message_request_id(event, "breakthrough"),
        )
    except EconomyError as exc:
        await breakthrough_matcher.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Cultivation breakthrough failed")
        await breakthrough_matcher.finish("突破失败，请稍后再试。")
    await breakthrough_matcher.finish(
        MessageSegment.at(event.user_id) + f" 突破成功！当前境界：{profile.realm_name}"
    )
