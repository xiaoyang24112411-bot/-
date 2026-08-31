"""Optional SauceNAO reverse-image lookup command."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_media_settings
from src.services.economy import EconomyError
from src.services.economy.commands import command_text
from src.services.media.message_image import image_url_from_event
from src.services.media.saucenao import search_image_source


def is_image_source(event: GroupMessageEvent) -> bool:
    return command_text(event, "图片来源") is not None


image_source = on_message(rule=Rule(is_image_source), priority=10, block=True)


@image_source.handle()
async def handle_image_source(bot: Bot, event: GroupMessageEvent) -> None:
    try:
        image_url = await image_url_from_event(bot, event)
        result = await search_image_source(
            image_url,
            get_media_settings().saucenao_api_key,
        )
    except EconomyError as exc:
        await image_source.finish(str(exc))
    except Exception:
        logger.exception("Reverse image lookup failed")
        await image_source.finish("图片来源查询失败，请稍后再试。")
    source = result.source_url or "结果未提供链接"
    await image_source.finish(
        MessageSegment.at(event.user_id)
        + f" 相似度：{result.similarity:.1f}%\n作品：{result.title}\n"
        f"作者：{result.author}\n来源：{source}"
    )
