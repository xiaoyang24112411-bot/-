"""Daily check-in and point balance commands."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_economy_settings
from src.services.economy import EconomyError, get_economy_database
from src.services.economy.accounts import get_account
from src.services.economy.checkin import check_in
from src.services.economy.commands import command_text


def is_checkin(event: GroupMessageEvent) -> bool:
    return command_text(event, "签到") is not None


def is_points(event: GroupMessageEvent) -> bool:
    return command_text(event, "积分") is not None or command_text(event, "我的积分") is not None


checkin = on_message(rule=Rule(is_checkin), priority=10, block=True)
points = on_message(rule=Rule(is_points), priority=10, block=True)


@checkin.handle()
async def handle_checkin(event: GroupMessageEvent) -> None:
    settings = get_economy_settings()
    try:
        result = await check_in(
            get_economy_database(),
            event.group_id,
            event.user_id,
            settings.checkin_reward_min,
            settings.checkin_reward_max,
        )
    except EconomyError as exc:
        await checkin.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Daily check-in failed")
        await checkin.finish("签到失败，请稍后再试。")

    await checkin.finish(
        MessageSegment.at(event.user_id)
        + f" 签到成功，获得 {result.reward} 积分！\n当前积分：{result.balance}"
    )


@points.handle()
async def handle_points(event: GroupMessageEvent) -> None:
    try:
        account = await get_account(get_economy_database(), event.group_id, event.user_id)
    except Exception:
        logger.exception("Point balance lookup failed")
        await points.finish("积分查询失败，请稍后再试。")
    await points.finish(
        MessageSegment.at(event.user_id) + f" 当前积分：{account.balance}\n"
        f"累计获得：{account.total_earned}\n累计支出：{account.total_spent}"
    )
