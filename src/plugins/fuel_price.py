"""Regional daily fuel price command."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_information_settings
from src.services.economy.commands import command_text
from src.services.information import InformationError
from src.services.information.api_60s import fetch_fuel_price


def is_fuel_price(event: GroupMessageEvent) -> bool:
    return (
        command_text(event, "今日油价") is not None or command_text(event, "每日油价") is not None
    )


fuel_price = on_message(rule=Rule(is_fuel_price), priority=10, block=True)


@fuel_price.handle()
async def handle_fuel_price(event: GroupMessageEvent) -> None:
    region = command_text(event, "今日油价")
    if region is None:
        region = command_text(event, "每日油价") or ""
    settings = get_information_settings()
    try:
        result = await fetch_fuel_price(
            settings.api_60s_base_url,
            region,
            timeout=settings.timeout_seconds,
        )
    except InformationError as exc:
        await fuel_price.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Fuel price lookup failed")
        await fuel_price.finish("油价查询失败，请稍后再试。")

    lines = [f"{result.region}今日油价"]
    lines.extend(f"{item.name}：{item.price_description}" for item in result.items)
    lines.extend((result.trend, f"更新时间：{result.updated}", "油价仅供参考，以加油站为准。"))
    await fuel_price.finish(MessageSegment.at(event.user_id) + "\n" + "\n".join(lines))
