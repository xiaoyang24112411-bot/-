"""Resolve an image segment from a message or its replied-to message."""

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message

from src.services.economy.errors import EconomyError


async def message_with_reply(bot: Bot, event: GroupMessageEvent) -> Message:
    message = event.get_message()
    for segment in message:
        if segment.type != "reply":
            continue
        message_id = segment.data.get("id")
        if message_id is None:
            continue
        replied = await bot.get_msg(message_id=int(message_id))
        return Message(replied.get("message", []))
    return message


async def image_url_from_event(bot: Bot, event: GroupMessageEvent) -> str:
    message = await message_with_reply(bot, event)
    for segment in message:
        if segment.type != "image":
            continue
        url = str(segment.data.get("url") or segment.data.get("file") or "").strip()
        if url:
            return url
    raise EconomyError("请在指令中附带图片，或回复一张图片后发送指令。")
