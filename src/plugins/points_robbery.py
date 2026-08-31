"""Point robbery mini-game command."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_economy_settings
from src.services.economy import EconomyError, get_economy_database
from src.services.economy.commands import command_text, message_request_id
from src.services.economy.robbery import play_robbery


def is_robbery(event: GroupMessageEvent) -> bool:
    return command_text(event, "打劫") is not None


robbery = on_message(rule=Rule(is_robbery), priority=10, block=True)


@robbery.handle()
async def handle_robbery(event: GroupMessageEvent) -> None:
    settings = get_economy_settings()
    try:
        result = await play_robbery(
            get_economy_database(),
            group_id=event.group_id,
            user_id=event.user_id,
            request_id=message_request_id(event, "robbery"),
            cooldown_seconds=settings.robbery_cooldown_seconds,
        )
    except EconomyError as exc:
        await robbery.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Robbery mini-game failed")
        await robbery.finish("打劫失败，请稍后再试。")

    if result.result_code == "success":
        message = f"打劫成功，获得 {result.change_amount} 积分！"
    elif result.result_code == "loss":
        message = f"打劫失败，损失 {-result.change_amount} 积分。"
    else:
        message = "扑了个空，本次积分没有变化。"
    await robbery.finish(
        MessageSegment.at(event.user_id) + f" {message}\n当前积分：{result.balance}"
    )
