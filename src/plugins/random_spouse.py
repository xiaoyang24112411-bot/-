"""Mutual daily spouse pairing, release and participation controls."""

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
    get_daily_spouse,
    set_spouse_pool_participation,
    unlink_daily_spouse,
)


def is_daily_spouse(event: GroupMessageEvent) -> bool:
    return any(
        command_text(event, name) == "" for name in ("今日老婆", "随机老婆", "抽老婆")
    )


def is_force_spouse(event: GroupMessageEvent) -> bool:
    return command_text(event, "强娶") is not None


def is_my_spouse(event: GroupMessageEvent) -> bool:
    return any(command_text(event, name) == "" for name in ("我的老婆", "查询老婆"))


def is_unlink_spouse(event: GroupMessageEvent) -> bool:
    return any(command_text(event, name) == "" for name in ("解绑老婆", "解绑群友老婆"))


def is_leave_pool(event: GroupMessageEvent) -> bool:
    return command_text(event, "退出老婆池") == ""


def is_join_pool(event: GroupMessageEvent) -> bool:
    return command_text(event, "加入老婆池") == ""


daily_spouse = on_message(rule=Rule(is_daily_spouse), priority=10, block=True)
force_spouse = on_message(rule=Rule(is_force_spouse), priority=10, block=True)
my_spouse = on_message(rule=Rule(is_my_spouse), priority=10, block=True)
unlink_spouse = on_message(rule=Rule(is_unlink_spouse), priority=10, block=True)
leave_pool = on_message(rule=Rule(is_leave_pool), priority=10, block=True)
join_pool = on_message(rule=Rule(is_join_pool), priority=10, block=True)


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
        + f" {label}\n今日绑定在明天 0 点刷新；双方都可发送「解绑老婆」。"
    )
    avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={result.spouse_user_id}&s=640"
    avatar_message = (
        MessageSegment.at(event.user_id)
        + f" {title}\n"
        + MessageSegment.image(avatar_url)
        + "\n就是 "
        + MessageSegment.at(result.spouse_user_id)
        + f" {label}\n今日绑定在明天 0 点刷新；双方都可发送「解绑老婆」。"
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

    await _send_result(bot, event, result, "你今天绑定的群友老婆：")


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

    await _send_result(bot, event, result, "强娶成功！你今天绑定的群友老婆：")


@my_spouse.handle()
async def handle_my_spouse(bot: Bot, event: GroupMessageEvent) -> None:
    try:
        result = await get_daily_spouse(
            get_economy_database(), group_id=event.group_id, user_id=event.user_id
        )
    except Exception:
        logger.exception("Daily spouse lookup failed")
        await my_spouse.finish("查询今日绑定失败，请稍后再试。")
    if result is None:
        await my_spouse.finish("你今天还没有绑定的群友老婆。发送「今日老婆」可抽取。")
    await _send_result(bot, event, result, "你今天绑定的群友老婆：")


@unlink_spouse.handle()
async def handle_unlink_spouse(event: GroupMessageEvent) -> None:
    try:
        result = await unlink_daily_spouse(
            get_economy_database(), group_id=event.group_id, user_id=event.user_id
        )
    except EconomyError as exc:
        await unlink_spouse.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Daily spouse unlink failed")
        await unlink_spouse.finish("解绑失败，请稍后再试。")
    if result.was_mutual_binding:
        await unlink_spouse.finish(
            MessageSegment.at(event.user_id)
            + " 已解除与 " + MessageSegment.at(result.partner_user_id)
            + " 的今日绑定。今天已用过的随机抽取不会重置；双方现在可另行强娶。"
        )
    await unlink_spouse.finish("已解除今天的旧抽取记录，现在可强娶未绑定的群友。")


@leave_pool.handle()
async def handle_leave_pool(event: GroupMessageEvent) -> None:
    try:
        changed, released = await set_spouse_pool_participation(
            get_economy_database(), group_id=event.group_id, user_id=event.user_id,
            participating=False,
        )
    except Exception:
        logger.exception("Daily spouse opt-out failed")
        await leave_pool.finish("退出老婆池失败，请稍后再试。")
    status = "已退出" if changed else "已经退出"
    suffix = "，同时已解除今日绑定" if released else ""
    await leave_pool.finish(f"{status}本群老婆池{suffix}；此后不会被随机抽中或强娶。")


@join_pool.handle()
async def handle_join_pool(event: GroupMessageEvent) -> None:
    try:
        changed, _ = await set_spouse_pool_participation(
            get_economy_database(), group_id=event.group_id, user_id=event.user_id,
            participating=True,
        )
    except Exception:
        logger.exception("Daily spouse opt-in failed")
        await join_pool.finish("加入老婆池失败，请稍后再试。")
    status = "已加入" if changed else "已经在"
    await join_pool.finish(f"{status}本群老婆池；不会自动恢复先前解除的绑定。")
