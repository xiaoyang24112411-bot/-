"""Regional daily fuel price command."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_information_settings
from src.services.information import InformationError
from src.services.information.api_60s import fetch_fuel_price
from src.services.information.commands import parse_fuel_region


def fuel_region(event: MessageEvent) -> str | None:
    return parse_fuel_region(event.get_plaintext())


def is_fuel_price(event: MessageEvent) -> bool:
    return fuel_region(event) is not None


def _reply(event: MessageEvent, text: str):
    if isinstance(event, GroupMessageEvent):
        return MessageSegment.at(event.user_id) + f" {text}"
    return MessageSegment.text(text)


fuel_price = on_message(rule=Rule(is_fuel_price), priority=10, block=True)


@fuel_price.handle()
async def handle_fuel_price(event: MessageEvent) -> None:
    region = fuel_region(event) or ""
    settings = get_information_settings()
    try:
        result = await fetch_fuel_price(
            settings.api_60s_base_url,
            region,
            timeout=settings.timeout_seconds,
        )
    except InformationError as exc:
        await fuel_price.finish(_reply(event, str(exc)))
    except Exception:
        logger.exception("Fuel price lookup failed")
        await fuel_price.finish("油价查询失败，请稍后再试。")

    lines = [f"{result.region}今日油价"]
    lines.extend(f"{item.name}：{item.price_description}" for item in result.items)
    lines.extend((result.trend, f"更新时间：{result.updated}", "油价仅供参考，以加油站为准。"))
    await fuel_price.finish(_reply(event, "\n".join(lines)))
