"""Point red packet commands."""

import re

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_economy_settings
from src.services.economy import EconomyError, get_economy_database
from src.services.economy.commands import command_text, message_request_id
from src.services.economy.red_packets import claim_red_packet, create_red_packet


def is_create_packet(event: GroupMessageEvent) -> bool:
    return command_text(event, "发红包") is not None


def is_claim_packet(event: GroupMessageEvent) -> bool:
    return command_text(event, "抢红包") is not None


create_packet = on_message(rule=Rule(is_create_packet), priority=10, block=True)
claim_packet = on_message(rule=Rule(is_claim_packet), priority=10, block=True)


@create_packet.handle()
async def handle_create_packet(event: GroupMessageEvent) -> None:
    argument = command_text(event, "发红包") or ""
    numbers = re.findall(r"(?<!\d)\d+(?!\d)", argument)
    if len(numbers) != 2:
        await create_packet.finish("用法：发红包 总积分 份数\n例如：发红包 100 5")
    settings = get_economy_settings()
    try:
        packet = await create_red_packet(
            get_economy_database(),
            group_id=event.group_id,
            sender_user_id=event.user_id,
            total_amount=int(numbers[0]),
            total_count=int(numbers[1]),
            request_id=message_request_id(event, "packet-create"),
            ttl_seconds=settings.red_packet_ttl_seconds,
        )
    except EconomyError as exc:
        await create_packet.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Red packet creation failed")
        await create_packet.finish("红包发送失败，请稍后再试。")

    await create_packet.finish(
        f"积分红包来啦！共 {packet.total_amount} 积分、{packet.total_count} 份。\n"
        f"红包编号：{packet.short_id}\n发送“抢红包”即可领取。"
    )


@claim_packet.handle()
async def handle_claim_packet(event: GroupMessageEvent) -> None:
    token = (command_text(event, "抢红包") or "").strip() or None
    if token is not None and not re.fullmatch(r"[0-9a-fA-F]{4,32}", token):
        await claim_packet.finish("用法：抢红包 [红包编号]")
    try:
        result = await claim_red_packet(
            get_economy_database(),
            group_id=event.group_id,
            user_id=event.user_id,
            packet_token=token,
            request_id=message_request_id(event, "packet-claim"),
        )
    except EconomyError as exc:
        await claim_packet.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Red packet claim failed")
        await claim_packet.finish("抢红包失败，请稍后再试。")

    await claim_packet.finish(
        MessageSegment.at(event.user_id)
        + f" 抢到 {result.amount} 积分！当前积分：{result.balance}\n"
        f"红包还剩 {result.remaining_count} 份。"
    )
