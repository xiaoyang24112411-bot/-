"""Daily persisted fortune command."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.services.economy import get_economy_database
from src.services.economy.commands import command_text
from src.services.entertainment.daily_fortune import draw_daily_fortune


def is_daily_fortune(event: GroupMessageEvent) -> bool:
    return (
        command_text(event, "每日运势") is not None or command_text(event, "今日运势") is not None
    )


daily_fortune = on_message(rule=Rule(is_daily_fortune), priority=10, block=True)


@daily_fortune.handle()
async def handle_daily_fortune(event: GroupMessageEvent) -> None:
    try:
        result = await draw_daily_fortune(
            get_economy_database(),
            group_id=event.group_id,
            user_id=event.user_id,
        )
    except Exception:
        logger.exception("Daily fortune draw failed")
        await daily_fortune.finish("每日运势抽取失败，请稍后再试。")

    await daily_fortune.finish(
        MessageSegment.at(event.user_id)
        + f" 今日运势：{result.fortune_level}（{result.score}分）\n"
        f"{result.summary}\n"
        f"幸运色：{result.lucky_color}｜幸运数字：{result.lucky_number}\n"
        f"幸运方位：{result.lucky_direction}｜幸运物：{result.lucky_item}\n"
        "结果每天 0 点刷新。"
    )
