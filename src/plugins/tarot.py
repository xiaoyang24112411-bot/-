"""One-card tarot reading command."""

from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.services.economy.commands import command_text
from src.services.entertainment.tarot import draw_tarot


def is_tarot(event: GroupMessageEvent) -> bool:
    return (
        command_text(event, "魔法占卜") is not None or command_text(event, "塔罗占卜") is not None
    )


tarot = on_message(rule=Rule(is_tarot), priority=10, block=True)


@tarot.handle()
async def handle_tarot(event: GroupMessageEvent) -> None:
    result = draw_tarot()
    await tarot.finish(
        MessageSegment.at(event.user_id) + f" 你抽到了：{result.card_name}·{result.orientation}\n"
        f"牌义：{result.interpretation}\n"
        "提示：占卜仅供娱乐，请把现实信息和自己的判断放在第一位。"
    )
