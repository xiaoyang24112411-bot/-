"""Manga metadata search backed by MangaDex."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_information_settings
from src.services.economy.commands import command_text
from src.services.information import InformationError
from src.services.information.mangadex import search_manga

manga_search = on_message(
    rule=Rule(lambda event: command_text(event, "漫画搜索") is not None),
    priority=10,
    block=True,
)


@manga_search.handle()
async def handle_manga_search(event: GroupMessageEvent) -> None:
    query = command_text(event, "漫画搜索") or ""
    settings = get_information_settings()
    try:
        results = await search_manga(
            settings.mangadex_base_url,
            query,
            timeout=settings.timeout_seconds,
        )
    except InformationError as exc:
        await manga_search.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Manga search failed")
        await manga_search.finish("漫画搜索失败，请稍后再试。")

    lines = ["MangaDex 漫画资料（仅返回检索与详情入口）"]
    for index, item in enumerate(results[:3], start=1):
        description = item.description.replace("\n", " ")
        if len(description) > 100:
            description = description[:100] + "……"
        lines.extend(
            (
                f"{index}. {item.title}｜{item.year}｜{item.status}",
                description,
                item.detail_url,
            )
        )
    await manga_search.finish("\n".join(lines))
