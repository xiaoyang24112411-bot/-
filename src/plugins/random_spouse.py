"""Daily spouse draw and once-per-day forced selection."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment
from nonebot.exception import ActionFailed
from nonebot.rule import Rule

from src.services.economy import EconomyError, get_economy_database
from src.services.economy.commands import command_text, mentioned_user
from src.services.entertainment.random_spouse import (
    DailySpouseResult,
    SpouseCandidate,
    draw_daily_spouse,
    force_daily_spouse,
)


def is_daily_spouse(event: GroupMessageEvent) -> bool:
    return command_text(event, "今日老婆") is not None


def is_force_spouse(event: GroupMessageEvent) -> bool:
    return command_text(event, "强娶") is not None


daily_spouse = on_message(rule=Rule(is_daily_spouse), priority=10, block=True)
force_spouse = on_message(rule=Rule(is_force_spouse), priority=10, block=True)


async def _group_candidates(bot: Bot, group_id: int) -> list[SpouseCandidate]:
    members = await bot.get_group_member_list(group_id=group_id)
    candidates = []
    for member in members:
        member_id = int(member.get("user_id", 0))
        if member_id <= 0 or member_id == int(bot.self_id):
            continue
        display_name = str(member.get("card") or member.get("nickname") or "").strip()
        candidates.append(SpouseCandidate(member_id, display_name[:50]))
    return candidates


async def _send_result(
    bot: Bot,
    event: GroupMessageEvent,
    result: DailySpouseResult,
    title: str,
) -> None:
    label = f"（{result.spouse_name}）" if result.spouse_name else ""
    text_message = (
        MessageSegment.at(event.user_id)
        + f" {title} "
        + MessageSegment.at(result.spouse_user_id)
        + f" {label}\n结果每天 0 点刷新。"
    )
    avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={result.spouse_user_id}&s=640"
    avatar_message = (
        MessageSegment.at(event.user_id)
        + f" {title}\n"
        + MessageSegment.image(avatar_url)
        + "\n就是 "
        + MessageSegment.at(result.spouse_user_id)
        + f" {label}\n结果每天 0 点刷新。"
    )
    try:
        await bot.send(event, avatar_message)
    except ActionFailed:
        logger.warning("QQ avatar image send failed; falling back to text-only spouse result")
        await bot.send(event, text_message)


@daily_spouse.handle()
async def handle_daily_spouse(bot: Bot, event: GroupMessageEvent) -> None:
    try:
        result = await draw_daily_spouse(
            get_economy_database(),
            group_id=event.group_id,
            user_id=event.user_id,
            candidates=await _group_candidates(bot, event.group_id),
        )
    except EconomyError as exc:
        await daily_spouse.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Daily spouse draw failed")
        await daily_spouse.finish("今日老婆抽取失败，请稍后再试。")

    await _send_result(bot, event, result, "你今天的群老婆头像：")


@force_spouse.handle()
async def handle_force_spouse(bot: Bot, event: GroupMessageEvent) -> None:
    target_id = mentioned_user(event)
    if target_id is None:
        await force_spouse.finish("用法：强娶 @群友")

    try:
        candidates = await _group_candidates(bot, event.group_id)
        target = next(
            (candidate for candidate in candidates if candidate.user_id == target_id),
            None,
        )
        if target is None:
            raise EconomyError("只能强娶当前群内的群友。")
        result = await force_daily_spouse(
            get_economy_database(),
            group_id=event.group_id,
            user_id=event.user_id,
            target=target,
        )
    except EconomyError as exc:
        await force_spouse.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Forced spouse selection failed")
        await force_spouse.finish("强娶失败，请稍后再试。")

    await _send_result(bot, event, result, "强娶成功！你今天的群老婆头像：")
