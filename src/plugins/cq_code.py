"""Reply-based raw OneBot/CQ message inspection."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.rule import Rule

from src.services.economy.commands import command_text


def is_cq_code(event: GroupMessageEvent) -> bool:
    return command_text(event, "取CQ码") is not None


cq_code = on_message(rule=Rule(is_cq_code), priority=10, block=True)


@cq_code.handle()
async def handle_cq_code(bot: Bot, event: GroupMessageEvent) -> None:
    reply_id = next(
        (segment.data.get("id") for segment in event.get_message() if segment.type == "reply"),
        None,
    )
    if reply_id is None:
        await cq_code.finish("请回复一条消息后发送“取CQ码”。")
    try:
        data = await bot.get_msg(message_id=int(reply_id))
        raw = str(data.get("raw_message") or Message(data.get("message", [])))
    except Exception:
        logger.exception("CQ code lookup failed")
        await cq_code.finish("读取被回复消息失败。")
    if len(raw) > 3000:
        raw = raw[:3000] + "……"
    await cq_code.finish(MessageSegment.text("CQ码：\n" + raw))
