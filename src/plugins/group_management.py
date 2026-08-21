"""Welcome new members and optionally recall sensitive group messages."""

from nonebot import logger, on_message, on_notice
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupIncreaseNoticeEvent,
    GroupMessageEvent,
    MessageSegment,
)
from nonebot.rule import Rule

from src.config import get_app_settings

settings = get_app_settings()

welcome = on_notice(priority=10, block=False)


@welcome.handle()
async def handle_welcome(event: GroupIncreaseNoticeEvent) -> None:
    await welcome.finish(MessageSegment.at(event.user_id) + " 欢迎加入本群！")


def contains_sensitive_word(event: GroupMessageEvent) -> bool:
    if not settings.enable_sensitive_recall:
        return False
    plain_text = event.get_plaintext()
    return any(word in plain_text for word in settings.sensitive_words)


sensitive_message = on_message(
    rule=Rule(contains_sensitive_word),
    priority=5,
    block=True,
)


@sensitive_message.handle()
async def handle_sensitive_message(bot: Bot, event: GroupMessageEvent) -> None:
    try:
        await bot.delete_msg(message_id=event.message_id)
        await sensitive_message.finish(
            MessageSegment.at(event.user_id) + " 消息包含敏感词，已自动撤回。"
        )
    except Exception:
        logger.exception("撤回群消息失败，请确认机器人具有管理员权限")

