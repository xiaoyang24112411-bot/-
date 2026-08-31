"""Point-backed Russian roulette command."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_economy_settings
from src.services.economy import EconomyError, get_economy_database
from src.services.economy.commands import command_text, message_request_id
from src.services.games.roulette import play_roulette


def is_roulette(event: GroupMessageEvent) -> bool:
    return command_text(event, "俄罗斯轮盘") is not None


roulette = on_message(rule=Rule(is_roulette), priority=10, block=True)


@roulette.handle()
async def handle_roulette(event: GroupMessageEvent) -> None:
    argument = (command_text(event, "俄罗斯轮盘") or "").strip()
    if not argument.isdigit():
        await roulette.finish("用法：俄罗斯轮盘 积分数\n例如：俄罗斯轮盘 10")
    settings = get_economy_settings()
    try:
        result = await play_roulette(
            get_economy_database(),
            group_id=event.group_id,
            user_id=event.user_id,
            wager=int(argument),
            request_id=message_request_id(event, "roulette"),
            cooldown_seconds=settings.roulette_cooldown_seconds,
            max_wager=settings.roulette_max_wager,
        )
    except EconomyError as exc:
        await roulette.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Russian roulette failed")
        await roulette.finish("俄罗斯轮盘执行失败，请稍后再试。")

    if result.result_code == "hit":
        message = f"砰！子弹击发，损失 {result.wager} 积分。"
    else:
        message = f"咔哒——安全！获得 {result.change_amount} 积分。"
    await roulette.finish(
        MessageSegment.at(event.user_id)
        + f" 第 {result.chamber} 号弹膛：{message}\n当前积分：{result.balance}"
    )
