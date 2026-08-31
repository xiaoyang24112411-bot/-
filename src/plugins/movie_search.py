"""Legal movie and TV metadata search backed by TMDB."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_information_settings
from src.services.economy.commands import command_text
from src.services.information import InformationError
from src.services.information.tmdb import search_screen_titles

movie_search = on_message(
    rule=Rule(lambda event: command_text(event, "影视搜索") is not None),
    priority=10,
    block=True,
)


@movie_search.handle()
async def handle_movie_search(event: GroupMessageEvent) -> None:
    query = command_text(event, "影视搜索") or ""
    settings = get_information_settings()
    try:
        results = await search_screen_titles(
            settings.tmdb_base_url,
            settings.tmdb_access_token,
            query,
            timeout=settings.timeout_seconds,
        )
    except InformationError as exc:
        await movie_search.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Movie search failed")
        await movie_search.finish("影视搜索失败，请稍后再试。")

    lines = ["TMDB 影视资料（不提供盗版播放链接）"]
    for index, item in enumerate(results[:3], start=1):
        overview = item.overview.replace("\n", " ")
        if len(overview) > 120:
            overview = overview[:120] + "……"
        lines.extend(
            (
                f"{index}. {item.title}｜{item.media_type}｜{item.year}｜{item.score:.1f}分",
                overview,
                item.detail_url,
            )
        )
    await movie_search.finish("\n".join(lines))
