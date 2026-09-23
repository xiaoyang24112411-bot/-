"""Resolve an image segment from a message or its replied-to message."""

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message

from src.services.economy.errors import EconomyError


async def message_with_reply(bot: Bot, event: GroupMessageEvent) -> Message:
    # OneBot resolves replies before dispatch and normally removes their segment.
    if event.reply is not None:
        return event.reply.message
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
    direct_message = event.get_message()
    messages = [direct_message]
    replied_message = await message_with_reply(bot, event)
    if replied_message is not direct_message:
        messages.append(replied_message)
    for message in messages:
        for segment in message:
            if segment.type != "image":
                continue
            url = str(segment.data.get("url") or "").strip()
            if url:
                return url
            file_id = str(segment.data.get("file") or "").strip()
            if file_id.startswith(("https://", "http://")):
                return file_id
            if file_id:
                try:
                    result = await bot.call_api("get_image", file=file_id)
                    url = str(result.get("url") or "").strip()
                    if url:
                        return url
                except Exception:
                    pass
    raise EconomyError("请在指令中附带图片，或回复一张图片后发送指令。")
