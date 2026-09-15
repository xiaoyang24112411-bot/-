"""Multi-platform hot-search rankings."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_information_settings
from src.services.information import InformationError
from src.services.information.api_60s import HOT_PLATFORMS, fetch_hot_search
from src.services.information.commands import parse_hot_search_platform


def _platform(event: MessageEvent) -> str | None:
    return parse_hot_search_platform(event.get_plaintext())


def _reply(event: MessageEvent, text: str):
    if isinstance(event, GroupMessageEvent):
        return MessageSegment.at(event.user_id) + f" {text}"
    return MessageSegment.text(text)


hot_search = on_message(
    rule=Rule(lambda event: _platform(event) is not None), priority=10, block=True
)
hot_search_platforms = on_message(
    rule=Rule(lambda event: event.get_plaintext().strip() in {"热搜平台", "/热搜平台"}),
    priority=10,
    block=True,
)


def _human_hot_value(value: str) -> str:
    if not value.isdigit():
        return value
    number = int(value)
    if number >= 10_000:
        return f"{number / 10_000:.1f}万"
    return str(number)


@hot_search.handle()
async def handle_hot_search(event: MessageEvent) -> None:
    platform = (_platform(event) or "微博").strip() or "微博"
    settings = get_information_settings()
    try:
        results = await fetch_hot_search(
            settings.api_60s_base_url,
            platform,
            limit=settings.hot_search_limit,
            timeout=settings.timeout_seconds,
        )
    except InformationError as exc:
        await hot_search.finish(_reply(event, str(exc)))
    except Exception:
        logger.exception("Hot-search lookup failed")
        await hot_search.finish("热搜查询失败，请稍后再试。")

    lines = [f"{platform}实时热搜"]
    for index, item in enumerate(results, start=1):
        suffix = f"（{_human_hot_value(item.hot_value)}）" if item.hot_value else ""
        lines.append(f"{index}. {item.title}{suffix}")
    await hot_search.finish("\n".join(lines))


@hot_search_platforms.handle()
async def handle_hot_search_platforms() -> None:
    platforms = "、".join(dict.fromkeys(HOT_PLATFORMS))
    await hot_search_platforms.finish("可用热搜平台：" + platforms)
