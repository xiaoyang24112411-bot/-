"""Group point transfer command."""

import re

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.services.economy import EconomyError, get_economy_database
from src.services.economy.commands import command_text, mentioned_user, message_request_id
from src.services.economy.transfer import transfer_points


def is_transfer(event: GroupMessageEvent) -> bool:
    return command_text(event, "转账") is not None


transfer = on_message(rule=Rule(is_transfer), priority=10, block=True)


@transfer.handle()
async def handle_transfer(event: GroupMessageEvent) -> None:
    target = mentioned_user(event)
    argument = command_text(event, "转账") or ""
    numbers = re.findall(r"(?<!\d)\d+(?!\d)", argument)
    if target is None or not numbers:
        await transfer.finish("用法：转账 @群友 积分数\n例如：转账 @群友 100")

    try:
        result = await transfer_points(
            get_economy_database(),
            group_id=event.group_id,
            sender_user_id=event.user_id,
            receiver_user_id=target,
            amount=int(numbers[-1]),
            request_id=message_request_id(event, "transfer"),
        )
    except EconomyError as exc:
        await transfer.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Point transfer failed")
        await transfer.finish("转账失败，请稍后再试。")

    await transfer.finish(
        MessageSegment.at(event.user_id)
        + " 已向 "
        + MessageSegment.at(target)
        + f" 转账 {result.amount} 积分。\n你的余额：{result.sender_balance}"
    )
