"""Image-to-ASCII command."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.services.economy import EconomyError
from src.services.economy.commands import command_text
from src.services.media.ascii_art import download_image, image_to_ascii
from src.services.media.message_image import image_url_from_event


def is_ascii_art(event: GroupMessageEvent) -> bool:
    return command_text(event, "图转字符") is not None


ascii_art = on_message(rule=Rule(is_ascii_art), priority=10, block=True)


@ascii_art.handle()
async def handle_ascii_art(bot: Bot, event: GroupMessageEvent) -> None:
    try:
        url = await image_url_from_event(bot, event)
        result = image_to_ascii(await download_image(url))
    except EconomyError as exc:
        await ascii_art.finish(str(exc))
    except Exception:
        logger.exception("Image-to-ASCII conversion failed")
        await ascii_art.finish("图转字符失败，请稍后再试。")
    await ascii_art.finish(MessageSegment.text("字符画：\n" + result))
