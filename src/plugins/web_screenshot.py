"""Public webpage screenshot command."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.services.economy import EconomyError
from src.services.economy.commands import command_text
from src.services.media.web_tools import screenshot_page


def is_web_screenshot(event: GroupMessageEvent) -> bool:
    return command_text(event, "网页截图") is not None


web_screenshot = on_message(rule=Rule(is_web_screenshot), priority=10, block=True)


@web_screenshot.handle()
async def handle_web_screenshot(event: GroupMessageEvent) -> None:
    url = (command_text(event, "网页截图") or "").strip()
    if not url:
        await web_screenshot.finish("用法：网页截图 https://example.com")
    try:
        image = await screenshot_page(url)
    except EconomyError as exc:
        await web_screenshot.finish(str(exc))
    except Exception:
        logger.exception("Web screenshot failed")
        await web_screenshot.finish("网页截图失败，请稍后再试。")
    await web_screenshot.finish(MessageSegment.image(image))
